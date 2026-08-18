"""DataUpdateCoordinator for Pool Comfort."""

import logging
import threading
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PoolComfort, PoolComfortConnectionError
from .const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SERIAL,
    DOMAIN,
    LOCAL_UDP_PORT,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)


class PoolComfortCoordinator(DataUpdateCoordinator[dict]):
    """Coordinator to manage fetching Pool Comfort data."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=SCAN_INTERVAL,
        )
        self.serial: str = config_entry.data[CONF_SERIAL]
        self.password: str = config_entry.data[CONF_PASSWORD]
        self.host: str | None = config_entry.data.get(CONF_HOST) or None
        self.api = PoolComfort(self.serial, self.password)
        self._lock = threading.Lock()

    @property
    def device_name(self) -> str:
        return self.api.device_name or "Pool Comfort"

    async def _async_update_data(self) -> dict:
        """Fetch data from the device."""
        try:
            return await self.hass.async_add_executor_job(self._sync_update)
        except Exception as err:
            raise UpdateFailed(f"Error communicating with device: {err}") from err

    def _sync_update(self) -> dict:
        """Fetch state in a fresh, serialized session with one retry."""
        with self._lock:
            last_error: Exception | None = None
            for attempt in range(2):
                self.api.close()
                try:
                    self._connect()
                    self.api.query_all_registers()
                    self.api.process_incoming(timeout=1)
                    return self.api.get_status()
                except Exception as err:  # noqa: BLE001 - transport errors vary
                    last_error = err
                    if attempt == 0:
                        _LOGGER.debug(
                            "Pool Comfort poll failed; retrying with a fresh session: %s",
                            err,
                        )
                finally:
                    self.api.close()

            if last_error is None:  # Defensive; both attempts always set this.
                raise PoolComfortConnectionError("Pool Comfort poll failed")
            raise last_error

    def set_temp(self, temp_c: int) -> bool:
        """Set the target temperature in a fresh session."""
        return self._sync_command(self.api.set_temp, temp_c)

    def set_mode(self, mode: int) -> bool:
        """Set the operating mode in a fresh session."""
        return self._sync_command(self.api.set_mode, mode)

    def set_power(self, on: bool) -> bool:
        """Set the power state in a fresh session."""
        return self._sync_command(self.api.set_power, on)

    def close(self) -> None:
        """Close the UDP client without racing an in-flight operation."""
        with self._lock:
            self.api.close()

    def _sync_command(self, command: Callable[[Any], bool], value: Any) -> bool:
        """Run one command without sharing a UDP session with a poll."""
        with self._lock:
            self.api.close()
            try:
                self._connect()
                return command(value)
            finally:
                self.api.close()

    def _connect(self) -> None:
        """Start a new local or cloud-relay session."""
        if self.host:
            self.api.connect(self.host, LOCAL_UDP_PORT)
        else:
            self.api.connect()
