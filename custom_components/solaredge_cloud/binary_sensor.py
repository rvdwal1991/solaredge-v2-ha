"""Problem sensor: on while SolarEdge reports an open alert."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SolarEdgeCloudConfigEntry
from .coordinator import SolarEdgeCloudCoordinator
from .sensor import site_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolarEdgeCloudConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([SolarEdgeAlertBinarySensor(entry.runtime_data)])


class SolarEdgeAlertBinarySensor(CoordinatorEntity[SolarEdgeCloudCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: SolarEdgeCloudCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.site_id}_problem"
        self._attr_device_info = site_device_info(coordinator)

    @property
    def is_on(self) -> bool | None:
        count = self.coordinator.data.get("open_alerts")
        return None if count is None else count > 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"alerts": self.coordinator.data.get("alerts", [])}
