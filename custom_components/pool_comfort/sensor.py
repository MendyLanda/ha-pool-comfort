"""Sensor platform for Pool Comfort."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PoolComfortCoordinator


@dataclass(kw_only=True, frozen=True)
class PoolComfortSensorDescription(SensorEntityDescription):
    """Describes a Pool Comfort sensor."""

    value_fn: Callable[[dict], float | int | None]


SENSOR_DESCRIPTIONS: tuple[PoolComfortSensorDescription, ...] = (
    PoolComfortSensorDescription(
        key="water_inlet",
        translation_key="water_inlet",
        name="Water Inlet Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: (data.get("temps") or {}).get("water_inlet"),
    ),
    PoolComfortSensorDescription(
        key="water_outlet",
        translation_key="water_outlet",
        name="Water Outlet Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: (data.get("temps") or {}).get("water_outlet"),
    ),
    PoolComfortSensorDescription(
        key="ambient",
        translation_key="ambient",
        name="Ambient Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: (data.get("temps") or {}).get("ambient"),
    ),
    PoolComfortSensorDescription(
        key="evaporator_coil",
        translation_key="evaporator_coil",
        name="Evaporator Coil Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (data.get("temps") or {}).get("evaporator_coil"),
    ),
    PoolComfortSensorDescription(
        key="discharge_gas",
        translation_key="discharge_gas",
        name="Discharge Gas Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (data.get("temps") or {}).get("discharge_gas"),
    ),
    PoolComfortSensorDescription(
        key="return_gas",
        translation_key="return_gas",
        name="Return Gas Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (data.get("temps") or {}).get("return_gas"),
    ),
    PoolComfortSensorDescription(
        key="eev_steps",
        translation_key="eev_steps",
        name="EEV Steps",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:valve",
        value_fn=lambda data: (data.get("temps") or {}).get("eev"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Pool Comfort sensors."""
    coordinator: PoolComfortCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PoolComfortSensor(coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    )


class PoolComfortSensor(CoordinatorEntity[PoolComfortCoordinator], SensorEntity):
    """Sensor entity for Pool Comfort."""

    entity_description: PoolComfortSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PoolComfortCoordinator,
        description: PoolComfortSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.serial}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.serial)},
            name=self.coordinator.device_name,
            manufacturer="Pool Comfort",
        )

    @property
    def native_value(self) -> float | int | None:
        """Return the sensor value."""
        if self.coordinator.data:
            return self.entity_description.value_fn(self.coordinator.data)
        return None
