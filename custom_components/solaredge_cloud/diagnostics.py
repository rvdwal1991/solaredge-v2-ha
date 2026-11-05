"""Diagnostics: raw API responses, without secrets."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import SolarEdgeCloudConfigEntry
from .const import CONF_CLIENT_SECRET, CONF_TOKEN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SolarEdgeCloudConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), {CONF_CLIENT_SECRET, CONF_TOKEN}),
        "token_expires_at": entry.data[CONF_TOKEN].get("expires_at"),
        "api_calls_today": coordinator.api_calls_today,
        "rate_limit_headers": coordinator.api.rate_limit,
        "parsed": async_redact_data(coordinator.data, {"site_name"}),
        "raw": async_redact_data(coordinator.raw, {"location", "name", "site_name", "accountId", "serialNumber", "connectedTo"}),
    }
