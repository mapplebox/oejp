from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import OEJPApi, OEJPApiError, OEJPAuthError
from .const import (
    DOMAIN,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_API_URL,
    DEFAULT_API_URL,
    DEFAULT_SCAN_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


class OEJPCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry

        self.api = OEJPApi(
            hass=hass,
            email=entry.data[CONF_EMAIL],
            password=entry.data[CONF_PASSWORD],
            api_url=entry.data.get(CONF_API_URL, DEFAULT_API_URL),
        )

        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS),
        )

    async def _async_update_data(self) -> dict:
        try:
            return await self.api.async_get_dashboard()
        except OEJPAuthError as err:
            raise UpdateFailed(str(err)) from err
        except OEJPApiError as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:
            _LOGGER.exception("OEJP unexpected error")
            raise UpdateFailed(str(err)) from err
