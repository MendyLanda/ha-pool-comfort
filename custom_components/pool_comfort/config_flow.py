"""Config flow for Pool Comfort integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .api import PoolComfort, PoolComfortConnectionError
from .const import DOMAIN, CONF_SERIAL, CONF_PASSWORD, DEFAULT_PASSWORD

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SERIAL): str,
        vol.Required(CONF_PASSWORD, default=DEFAULT_PASSWORD): str,
    }
)


class PoolComfortConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Pool Comfort."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            serial = user_input[CONF_SERIAL].strip()
            password = user_input[CONF_PASSWORD]

            await self.async_set_unique_id(serial)
            self._abort_if_unique_id_configured()

            # Validate connection
            try:
                api = PoolComfort(serial, password)
                await self.hass.async_add_executor_job(api.connect)
                api.close()
            except PoolComfortConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"Pool Comfort ({serial})",
                    data={CONF_SERIAL: serial, CONF_PASSWORD: password},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
