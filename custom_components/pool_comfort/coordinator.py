"""DataUpdateCoordinator for Pool Comfort."""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PoolComfort, PoolComfortConnectionError
from .const import DOMAIN, CONF_SERIAL, CONF_PASSWORD

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
        self.api = PoolComfort(self.serial, self.password)

    @property
    def device_name(self) -> str:
        return self.api.device_name or "Pool Comfort"

    async def _async_setup(self) -> None:
        """Connect to the device on first refresh."""
        try:
            await self.hass.async_add_executor_job(self.api.connect)
        except PoolComfortConnectionError as err:
            raise UpdateFailed(f"Failed to connect: {err}") from err

    async def _async_update_data(self) -> dict:
        """Fetch data from the device."""
        try:
            return await self.hass.async_add_executor_job(self._sync_update)
        except Exception as err:
            # Try reconnecting on failure
            self.api.close()
            try:
                await self.hass.async_add_executor_job(self.api.connect)
                return await self.hass.async_add_executor_job(self._sync_update)
            except Exception as reconnect_err:
                raise UpdateFailed(
                    f"Error communicating with device: {reconnect_err}"
                ) from reconnect_err

    def _sync_update(self) -> dict:
        """Synchronous update — runs in executor."""
        self.api.process_incoming(timeout=2)
        self.api.query_all_registers()
        self.api.process_incoming(timeout=1)
        return self.api.get_status()
