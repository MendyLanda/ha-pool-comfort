"""Binary sensor platform for Pool Comfort."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PoolComfortCoordinator


@dataclass(kw_only=True, frozen=True)
class PoolComfortBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a Pool Comfort binary sensor."""

    value_fn: Callable[[dict], bool | None]


BINARY_SENSOR_DESCRIPTIONS: tuple[PoolComfortBinarySensorDescription, ...] = (
    PoolComfortBinarySensorDescription(
        key="compressor",
        name="Compressor",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (data.get("working_details") or {}).get("compressor"),
    ),
    PoolComfortBinarySensorDescription(
        key="four_way_valve",
        name="Four-way Valve",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:valve",
        value_fn=lambda data: (data.get("working_details") or {}).get("four_way_valve"),
    ),
    PoolComfortBinarySensorDescription(
        key="high_fan",
        name="High Fan Speed",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (data.get("working_details") or {}).get("high_fan"),
    ),
    PoolComfortBinarySensorDescription(
        key="low_fan",
        name="Low Fan Speed",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (data.get("working_details") or {}).get("low_fan"),
    ),
    PoolComfortBinarySensorDescription(
        key="water_pump",
        name="Circulation Pump",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (data.get("working_details") or {}).get("water_pump"),
    ),
    PoolComfortBinarySensorDescription(
        key="electric_heater",
        name="Electric Heater",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (data.get("working_details") or {}).get("electric_heater"),
    ),
    PoolComfortBinarySensorDescription(
        key="bottom_heater",
        name="Bottom Heater",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (data.get("working_details") or {}).get("bottom_heater"),
    ),
    PoolComfortBinarySensorDescription(
        key="low_pressure",
        name="Low Pressure Switch",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (data.get("working_details") or {}).get("low_pressure"),
    ),
    PoolComfortBinarySensorDescription(
        key="high_pressure",
        name="High Pressure Switch",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (data.get("working_details") or {}).get("high_pressure"),
    ),
    PoolComfortBinarySensorDescription(
        key="waterflow_switch",
        name="Waterflow Switch",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:water-pump",
        value_fn=lambda data: (data.get("working_details") or {}).get("waterflow_switch"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Pool Comfort binary sensors."""
    coordinator: PoolComfortCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PoolComfortBinarySensor(coordinator, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class PoolComfortBinarySensor(
    CoordinatorEntity[PoolComfortCoordinator], BinarySensorEntity
):
    """Binary sensor entity for Pool Comfort."""

    entity_description: PoolComfortBinarySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PoolComfortCoordinator,
        description: PoolComfortBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
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
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        if self.coordinator.data:
            return self.entity_description.value_fn(self.coordinator.data)
        return None
