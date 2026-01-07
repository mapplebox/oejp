from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_YEN_PER_KWH, DEFAULT_YEN_PER_KWH
from .coordinator import OEJPCoordinator


def _safe_float(v) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


@dataclass(frozen=True)
class _SensorDef:
    key: str
    name: str
    device_class: SensorDeviceClass | None
    state_class: SensorStateClass | None
    unit: str | None


SENSORS: list[_SensorDef] = [
    _SensorDef("last_half_hour_kwh", "OEJP Last half hour", None, None, "kWh"),
    _SensorDef("last_half_hour_w", "OEJP Power", SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT, "W"),
    _SensorDef("today_kwh", "OEJP Today", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL, "kWh"),
    _SensorDef("yesterday_kwh", "OEJP Yesterday", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL, "kWh"),
    _SensorDef("month_to_date_kwh", "OEJP Month to date", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL, "kWh"),
    _SensorDef("last_month_kwh", "OEJP Last month", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL, "kWh"),
    _SensorDef("today_cost_yen", "OEJP Cost today", SensorDeviceClass.MONETARY, SensorStateClass.TOTAL, "JPY"),
    _SensorDef("month_to_date_cost_yen", "OEJP Cost month to date", SensorDeviceClass.MONETARY, SensorStateClass.TOTAL, "JPY"),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: OEJPCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []
    for s in SENSORS:
        entities.append(OEJPSensor(coordinator, s))

    entities.append(OEJPCumulativeEnergy(coordinator))

    async_add_entities(entities)


class OEJPSensor(CoordinatorEntity[OEJPCoordinator], SensorEntity):
    def __init__(self, coordinator: OEJPCoordinator, sdef: _SensorDef) -> None:
        super().__init__(coordinator)
        self._key = sdef.key
        self._attr_name = sdef.name
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{self._key}"

        self._attr_device_class = sdef.device_class
        self._attr_state_class = sdef.state_class
        self._attr_native_unit_of_measurement = sdef.unit

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        opts = self.coordinator.entry.options or {}
        yen_per_kwh = float(opts.get(CONF_YEN_PER_KWH, DEFAULT_YEN_PER_KWH))

        if self._key == "last_half_hour_w":
            kwh = _safe_float(data.get("last_half_hour_kwh"))
            if kwh is None:
                return None
            return round(kwh * 2000.0, 1)

        if self._key == "today_cost_yen":
            kwh = _safe_float(data.get("today_kwh"))
            if kwh is None:
                return None
            return round(kwh * yen_per_kwh, 0)

        if self._key == "month_to_date_cost_yen":
            kwh = _safe_float(data.get("month_to_date_kwh"))
            if kwh is None:
                return None
            return round(kwh * yen_per_kwh, 0)

        return data.get(self._key)

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        opts = self.coordinator.entry.options or {}
        yen_per_kwh = float(opts.get(CONF_YEN_PER_KWH, DEFAULT_YEN_PER_KWH))

        attrs: dict[str, Any] = {
            "account_number": data.get("account_number"),
            "yen_per_kwh": yen_per_kwh,
        }
        if self._key in ("last_half_hour_kwh", "last_half_hour_w"):
            attrs["last_interval_end_jst"] = data.get("last_interval_end_jst")
        return attrs


class OEJPCumulativeEnergy(CoordinatorEntity[OEJPCoordinator], RestoreEntity, SensorEntity):
    _attr_name = "OEJP Energy total"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = "kWh"

    def __init__(self, coordinator: OEJPCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_energy_total"
        self._total: float | None = None
        self._last_end: str | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state not in (None, "unknown", "unavailable"):
            try:
                self._total = float(last.state)
            except Exception:
                self._total = 0.0
        else:
            self._total = 0.0

        if last and last.attributes:
            self._last_end = last.attributes.get("last_interval_end_jst")

    @property
    def native_value(self):
        return self._total

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        return {
            "account_number": data.get("account_number"),
            "last_interval_end_jst": self._last_end,
        }

    def _apply_recent(self) -> None:
        data = self.coordinator.data or {}
        recent = data.get("recent_readings") or []
        if not isinstance(recent, list):
            return

        if self._total is None:
            self._total = 0.0

        new_last_end = self._last_end

        for item in recent:
            if not isinstance(item, dict):
                continue
            end_jst = item.get("end_jst")
            kwh = item.get("kwh")
            if not isinstance(end_jst, str):
                continue
            if not isinstance(kwh, (int, float)):
                continue

            if self._last_end is None or end_jst > self._last_end:
                self._total += float(kwh)
                new_last_end = end_jst

        self._last_end = new_last_end

    async def async_update(self) -> None:
        await super().async_update()
        self._apply_recent()
