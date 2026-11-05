"""Sensors for SolarEdge Cloud."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfMass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SolarEdgeCloudConfigEntry
from .const import DOMAIN
from .coordinator import SolarEdgeCloudCoordinator


@dataclass(frozen=True, kw_only=True)
class SolarEdgeSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]
    attr_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _energy(key: str) -> SolarEdgeSensorDescription:
    return SolarEdgeSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        value_fn=lambda d, key=key: d.get(key),
    )


SENSORS = (
    _energy("energy_today"),
    _energy("energy_this_month"),
    _energy("energy_this_year"),
    _energy("lifetime_energy"),
    SolarEdgeSensorDescription(
        key="specific_yield_today",
        translation_key="specific_yield_today",
        native_unit_of_measurement="kWh/kWp",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: d.get("specific_yield_today"),
    ),
    SolarEdgeSensorDescription(
        key="specific_yield_this_month",
        translation_key="specific_yield_this_month",
        native_unit_of_measurement="kWh/kWp",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.get("specific_yield_this_month"),
    ),
    SolarEdgeSensorDescription(
        key="open_alerts",
        translation_key="open_alerts",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("open_alerts"),
        attr_fn=lambda d: {"alerts": d.get("alerts", [])},
    ),
    SolarEdgeSensorDescription(
        key="co2_avoided",
        translation_key="co2_avoided",
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        suggested_display_precision=0,
        value_fn=lambda d: d.get("co2_avoided"),
        attr_fn=lambda d: {"equivalent_ev_km": d.get("ev_km")},
    ),
    SolarEdgeSensorDescription(
        key="optimizer_count",
        translation_key="optimizer_count",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("optimizer_count"),
        attr_fn=lambda d: {"models": d.get("optimizer_models"), "inverters": d.get("inverters")},
    ),
    SolarEdgeSensorDescription(
        key="site_status",
        translation_key="site_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("site_status"),
        attr_fn=lambda d: {"peak_power_kwp": d.get("peak_power"), "site_name": d.get("site_name")},
    ),
    SolarEdgeSensorDescription(
        key="last_update",
        translation_key="last_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("last_update"),
    ),
)


def site_device_info(coordinator: SolarEdgeCloudCoordinator) -> DeviceInfo:
    """One device per site; model and firmware of the (first) inverter."""
    inverter = next(iter(coordinator.data.get("inverters") or []), {})
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.site_id)},
        manufacturer="SolarEdge",
        name=f"SolarEdge site {coordinator.site_id}",
        model=inverter.get("model"),
        sw_version=inverter.get("firmware"),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolarEdgeCloudConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(SolarEdgeCloudSensor(coordinator, d) for d in SENSORS)


class SolarEdgeCloudSensor(CoordinatorEntity[SolarEdgeCloudCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: SolarEdgeSensorDescription

    def __init__(
        self, coordinator: SolarEdgeCloudCoordinator, description: SolarEdgeSensorDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.site_id}_{description.key}"
        self._attr_device_info = site_device_info(coordinator)

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attr_fn:
            return self.entity_description.attr_fn(self.coordinator.data)
        return None
