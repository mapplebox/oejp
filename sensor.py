from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OEJPCoordinator


@dataclass(frozen=True)
class _SensorDef:
    key: str
    name: str
    device_class: SensorDeviceClass | None
    state_class: SensorStateClass | None
    unit: str | None


SENSORS: list[_SensorDef] = [
    # Das ist ein Intervall-Wert. HA ist hier streng: energy + measurement passt nicht.
    # Wir lassen ihn als "None/None" damit es keine Warnung gibt, bleibt trotzdem kWh als Wert.
    _SensorDef("last_half_hour_kwh", "OEJP Last half hour", None, None, "kWh"),

    # Tageswerte sind Totals (Energy)
    _SensorDef("today_kwh", "OEJP Today", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL, "kWh"),
    _SensorDef("yesterday_kwh", "OEJP Yesterday", SensorDeviceClass.ENERGY, SensorStateClass.TOTAL, "kWh"),
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: OEJPCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OEJPSensor(coordinator, s) for s in SENSORS])


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
        return (self.coordinator.data or {}).get(self._key)

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        attrs = {"account_number": data.get("account_number")}
        if self._key == "last_half_hour_kwh":
            attrs["last_interval_end_jst"] = data.get("last_interval_end_jst")
        return attrs
