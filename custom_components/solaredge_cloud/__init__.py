"""SolarEdge Cloud: production data from the SolarEdge Monitoring API V2."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import SolarEdgeCloudCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

type SolarEdgeCloudConfigEntry = ConfigEntry[SolarEdgeCloudCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SolarEdgeCloudConfigEntry) -> bool:
    coordinator = SolarEdgeCloudCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SolarEdgeCloudConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
