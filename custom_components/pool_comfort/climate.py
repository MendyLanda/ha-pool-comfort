"""Climate platform for Pool Comfort."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PoolComfortCoordinator

# Pool Comfort mode values → HA HVAC modes
_MODE_TO_HVAC = {
    0: HVACMode.AUTO,
    1: HVACMode.COOL,
    2: HVACMode.HEAT,
}
_HVAC_TO_MODE = {v: k for k, v in _MODE_TO_HVAC.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Pool Comfort climate entity."""
    coordinator: PoolComfortCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PoolComfortClimate(coordinator)])


class PoolComfortClimate(CoordinatorEntity[PoolComfortCoordinator], ClimateEntity):
    """Climate entity for Pool Comfort heat pump."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 1.0
    _attr_min_temp = 15
    _attr_max_temp = 40
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.AUTO,
        HVACMode.COOL,
        HVACMode.HEAT,
    ]

    def __init__(self, coordinator: PoolComfortCoordinator) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.serial}_climate"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.serial)},
            name=self.coordinator.device_name,
            manufacturer="Pool Comfort",
        )

    @property
    def current_temperature(self) -> float | None:
        """Return the current water inlet temperature."""
        if self.coordinator.data:
            temps = self.coordinator.data.get("temps")
            if temps:
                return temps.get("water_inlet")
        return None

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        if self.coordinator.data:
            return self.coordinator.data.get("set_temp")
        return None

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        if self.coordinator.data:
            power = self.coordinator.data.get("power")
            if power is False:
                return HVACMode.OFF
            mode = self.coordinator.data.get("mode")
            if mode is not None:
                return _MODE_TO_HVAC.get(mode, HVACMode.AUTO)
        return HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return current HVAC action."""
        if self.coordinator.data:
            power = self.coordinator.data.get("power")
            if power is False:
                return HVACAction.OFF
            details = self.coordinator.data.get("working_details")
            compressor_on = details.get("compressor", False) if details else False
            mode = self.coordinator.data.get("mode")
            if compressor_on:
                if mode == 1:
                    return HVACAction.COOLING
                elif mode == 2:
                    return HVACAction.HEATING
                else:
                    # Auto mode — infer from four-way valve
                    if details and details.get("four_way_valve"):
                        return HVACAction.HEATING
                    return HVACAction.COOLING
            return HVACAction.IDLE
        return None

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        await self.hass.async_add_executor_job(
            self.coordinator.api.set_temp, int(temp)
        )
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self.hass.async_add_executor_job(
                self.coordinator.api.set_power, False
            )
        else:
            # Turn on if currently off
            if self.coordinator.data and self.coordinator.data.get("power") is False:
                await self.hass.async_add_executor_job(
                    self.coordinator.api.set_power, True
                )
            device_mode = _HVAC_TO_MODE.get(hvac_mode)
            if device_mode is not None:
                await self.hass.async_add_executor_job(
                    self.coordinator.api.set_mode, device_mode
                )
        await self.coordinator.async_request_refresh()
