"""Config flow for Pool Comfort integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .api import PoolComfort, PoolComfortConnectionError
from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SERIAL,
    DEFAULT_PASSWORD,
    DOMAIN,
    LOCAL_UDP_PORT,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SERIAL): str,
        vol.Required(CONF_PASSWORD, default=DEFAULT_PASSWORD): str,
        vol.Optional(CONF_HOST, default=""): str,
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
            data = self._normalize_input(user_input)
            serial = data[CONF_SERIAL]

            await self.async_set_unique_id(serial)
            self._abort_if_unique_id_configured()

            if (error := await self._async_validate_connection(data)) is not None:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=f"Pool Comfort ({serial})",
                    data=data,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow an existing entry to switch between local and cloud access."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            data = self._normalize_input(user_input)
            await self.async_set_unique_id(data[CONF_SERIAL])
            self._abort_if_unique_id_mismatch()

            if (error := await self._async_validate_connection(data)) is not None:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=data,
                )

        suggested_values = {
            **entry.data,
            CONF_HOST: entry.data.get(CONF_HOST, ""),
        }
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, suggested_values
            ),
            errors=errors,
        )

    @staticmethod
    def _normalize_input(user_input: dict[str, Any]) -> dict[str, str]:
        """Normalize values stored in the config entry."""
        return {
            CONF_SERIAL: user_input[CONF_SERIAL].strip(),
            CONF_PASSWORD: user_input[CONF_PASSWORD],
            CONF_HOST: user_input.get(CONF_HOST, "").strip(),
        }

    async def _async_validate_connection(self, data: dict[str, str]) -> str | None:
        """Validate local or cloud connectivity and always close the test socket."""
        api = PoolComfort(data[CONF_SERIAL], data[CONF_PASSWORD])
        host = data[CONF_HOST]
        try:
            if host:
                await self.hass.async_add_executor_job(
                    api.connect, host, LOCAL_UDP_PORT
                )
            else:
                await self.hass.async_add_executor_job(api.connect)
        except (PoolComfortConnectionError, OSError):
            return "cannot_connect"
        except Exception:
            _LOGGER.exception("Unexpected exception")
            return "unknown"
        finally:
            await self.hass.async_add_executor_job(api.close)
        return None
