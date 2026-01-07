from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .api import OEJPApi, OEJPAuthError, OEJPApiError
from .const import DOMAIN, CONF_EMAIL, CONF_PASSWORD, CONF_API_URL, DEFAULT_API_URL

_LOGGER = logging.getLogger(__name__)


async def _validate_input(hass: HomeAssistant, data: dict) -> None:
    api = OEJPApi(
        hass=hass,
        email=data[CONF_EMAIL],
        password=data[CONF_PASSWORD],
        api_url=data.get(CONF_API_URL) or DEFAULT_API_URL,
    )
    await api.async_test_auth()


class OEJPConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await _validate_input(self.hass, user_input)
                await self.async_set_unique_id(f"oejp_{user_input[CONF_EMAIL].lower()}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Octopus Energy Japan",
                    data={
                        CONF_EMAIL: user_input[CONF_EMAIL],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_API_URL: user_input.get(CONF_API_URL) or DEFAULT_API_URL,
                    },
                )
            except OEJPAuthError:
                errors["base"] = "auth"
            except OEJPApiError as e:
                _LOGGER.error("OEJP API error during config: %s", e)
                errors["base"] = "cannot_connect"
            except Exception as e:
                _LOGGER.exception("OEJP unexpected error during config: %s", e)
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_API_URL, default=DEFAULT_API_URL): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
