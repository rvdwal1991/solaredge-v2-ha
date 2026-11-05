"""Coordinator: token handling, credit-aware polling and parsing of V2 responses."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    SolarEdgeAuthError,
    SolarEdgeError,
    SolarEdgeNotFoundError,
    SolarEdgeRateLimitError,
    SolarEdgeV2,
    token_request,
)
from .const import (
    ALERTS_INTERVAL,
    BENEFITS_INTERVAL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_SITE_ID,
    CONF_TOKEN,
    DAY_INTERVAL_SUN_DOWN,
    DAY_INTERVAL_SUN_UP,
    DETAILS_INTERVAL,
    DEVICES_INTERVAL,
    DOMAIN,
    ERROR_BACKOFF,
    LIFETIME_INTERVAL,
    LOGGER,
    MONTH_INTERVAL,
    TICK_INTERVAL,
    YEAR_INTERVAL,
)


class SolarEdgeCloudCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Only calls an endpoint when its own interval has passed."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass, LOGGER, name=DOMAIN, update_interval=TICK_INTERVAL, config_entry=entry
        )
        self.site_id = str(entry.data[CONF_SITE_ID])
        self.api = SolarEdgeV2(async_get_clientsession(hass))
        self.raw: dict[str, Any] = {}
        self.api_calls_today = 0
        self._calls_date = dt_util.now().date()
        self._fetched_at: dict[str, datetime] = {}
        self._backoff_until: datetime | None = None
        self._token_lock = asyncio.Lock()

    # --- tokens -----------------------------------------------------------

    async def _access_token(self) -> str:
        async with self._token_lock:
            entry = self.config_entry
            token = entry.data[CONF_TOKEN]
            if token.get("expires_at", 0) - 300 > time.time():
                return token["access_token"]
            try:
                new = await token_request(
                    async_get_clientsession(self.hass),
                    entry.data[CONF_CLIENT_ID],
                    entry.data[CONF_CLIENT_SECRET],
                    {"grant_type": "refresh_token", "refresh_token": token["refresh_token"]},
                )
            except SolarEdgeAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except SolarEdgeError as err:
                raise UpdateFailed(str(err)) from err
            # SolarEdge rotates the refresh token on every use: store it right away.
            new.setdefault("refresh_token", token["refresh_token"])
            self.hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_TOKEN: new}
            )
            LOGGER.debug("Access token refreshed, valid until %s", new["expires_at"])
            return new["access_token"]

    async def _get(self, path: str, params: Any = None) -> Any:
        token = await self._access_token()
        today = dt_util.now().date()
        if today != self._calls_date:
            self._calls_date, self.api_calls_today = today, 0
        self.api_calls_today += 1
        return await self.api.get(token, path, params)

    # --- scheduling -------------------------------------------------------

    def _due(self, key: str, interval: timedelta, now: datetime) -> bool:
        last = self._fetched_at.get(key)
        return last is None or now - last >= interval

    def _sun_up(self) -> bool:
        sun = self.hass.states.get("sun.sun")
        return sun is None or sun.state == "above_horizon"

    async def _async_update_data(self) -> dict[str, Any]:
        now = dt_util.now()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = day_start.replace(day=1)
        year_start = month_start.replace(month=1)
        sid = self.site_id

        # New day/month/year: drop the cached value so the totals reset.
        for key, start in (("day", day_start), ("month", month_start), ("year", year_start)):
            if (last := self._fetched_at.get(key)) and last < start:
                self._fetched_at.pop(key)

        if self._backoff_until and now < self._backoff_until:
            return self._parse()

        day_interval = DAY_INTERVAL_SUN_UP if self._sun_up() else DAY_INTERVAL_SUN_DOWN
        plan: list[tuple[str, timedelta, str, Any]] = [
            ("details", DETAILS_INTERVAL, f"/sites/{sid}", None),
            ("day", day_interval, f"/sites/{sid}/overview",
             {"from": day_start.isoformat(), "to": now.isoformat()}),
            ("month", MONTH_INTERVAL, f"/sites/{sid}/energy",
             {"from": month_start.isoformat(), "to": now.isoformat(), "resolution": "TOTAL"}),
            ("year", YEAR_INTERVAL, f"/sites/{sid}/energy",
             {"from": year_start.isoformat(), "to": now.isoformat(), "resolution": "TOTAL"}),
            ("lifetime", LIFETIME_INTERVAL, f"/sites/{sid}/lifetime-energy", None),
            ("alerts", ALERTS_INTERVAL, f"/sites/{sid}/alerts",
             {"only-open": "true", "alerts-in-page": "50"}),
            ("benefits", BENEFITS_INTERVAL, f"/sites/{sid}/environmental-benefits", None),
            ("devices", DEVICES_INTERVAL, f"/sites/{sid}/devices",
             [("types", "INVERTER"), ("types", "OPTIMIZER")]),
        ]
        try:
            for key, interval, path, params in plan:
                if not self._due(key, interval, now):
                    continue
                try:
                    self.raw[key] = await self._get(path, params)
                except SolarEdgeNotFoundError:
                    self.raw[key] = None
                self._fetched_at[key] = now
        except SolarEdgeAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SolarEdgeError as err:
            # Don't retry every tick: that burns credits and floods the log.
            self._backoff_until = now + ERROR_BACKOFF
            if not self.raw:
                raise UpdateFailed(str(err)) from err
            LOGGER.warning(
                "SolarEdge %s, keeping last known values: %s",
                "rate limit reached" if isinstance(err, SolarEdgeRateLimitError) else "request failed",
                err,
            )

        return self._parse()

    # --- parsing ----------------------------------------------------------

    def _parse(self) -> dict[str, Any]:
        raw = self.raw
        details = _mapping(raw.get("details"))
        site = _mapping(details.get("site")) or details
        day = _mapping(raw.get("day"))
        production = _mapping(day.get("production"))
        lifetime = _mapping(raw.get("lifetime"))
        benefits = _mapping(raw.get("benefits"))
        alerts_raw = raw.get("alerts")
        if isinstance(alerts_raw, dict):
            alerts_raw = _find_list(alerts_raw, "alerts", "list")
        alerts = [a for a in alerts_raw or [] if isinstance(a, dict)]
        devices = raw.get("devices")
        devices = [
            d for d in (devices if isinstance(devices, list) else _device_list(devices))
            if isinstance(d, dict)
        ]
        inverters = [d for d in devices if d.get("type") == "INVERTER"]
        optimizers = [d for d in devices if d.get("type") == "OPTIMIZER"]
        peak_kwp = site.get("peakPower")

        energy_today = _kwh(
            _find_number(production, "total"),
            _find_string(production, "units", "unit") or _find_string(day, "units", "unit"),
        )
        energy_month = _energy_total_kwh(_mapping(raw.get("month")))
        ev_miles = _find_number(benefits, "evMiles")
        return {
            "energy_today": energy_today,
            "energy_this_month": energy_month,
            "energy_this_year": _energy_total_kwh(_mapping(raw.get("year"))),
            "lifetime_energy": _kwh(
                _find_number(lifetime, "energy", "lifetimeEnergy", "total"),
                _find_string(lifetime, "units", "unit"),
            ),
            "specific_yield_today": _per_kwp(energy_today, peak_kwp),
            "specific_yield_this_month": _per_kwp(energy_month, peak_kwp),
            "open_alerts": len(alerts) if isinstance(alerts_raw, list) else None,
            "alerts": [
                {
                    "type": a.get("type"),
                    "category": a.get("category"),
                    "impact": a.get("impact"),
                    "component": _mapping(a.get("component")).get("name"),
                    "first_trigger": a.get("firstTrigger"),
                    "last_trigger": a.get("lastTrigger"),
                    "error_codes": a.get("errorCodes") or [],
                }
                for a in alerts
            ],
            "co2_avoided": _find_number(benefits, "co2Emissions"),
            "ev_km": round(ev_miles * 1.609344) if ev_miles is not None else None,
            "inverters": [
                {
                    "name": i.get("name"),
                    "model": i.get("partNumber") or i.get("model"),
                    "firmware": i.get("firmwareVersion"),
                    "communication": i.get("communicationType"),
                    "optimizers": i.get("connectedOptimizers"),
                }
                for i in inverters
            ],
            "optimizer_count": len(optimizers) if devices else None,
            "optimizer_models": sorted(
                {o.get("model") or o.get("partNumber") for o in optimizers} - {None}
            ),
            "site_status": site.get("activationStatus") or site.get("status"),
            "site_name": site.get("name"),
            "peak_power": peak_kwp,
            "last_update": _parse_time(
                _find_string(day, "lastUpdateTime", "timestamp")
                or _find_string(site, "lastUpdateTime")
                or _find_string(lifetime, "lastUpdateTime", "timestamp")
            ),
        }


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _device_list(value: Any) -> list[dict[str, Any]]:
    return _find_list(value, "devices", "device") if isinstance(value, dict) else []


def _per_kwp(kwh: float | None, kwp: Any) -> float | None:
    if kwh is None or not isinstance(kwp, int | float) or not kwp:
        return None
    return round(kwh / kwp, 3)


def _find_list(data: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        if isinstance(value := data.get(key), list):
            return [item for item in value if isinstance(item, dict)]
    for value in data.values():
        if isinstance(value, dict) and (result := _find_list(value, *keys)):
            return result
    return []


def _find_number(data: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    for value in data.values():
        if isinstance(value, dict) and (result := _find_number(value, *keys)) is not None:
            return result
    return None


def _find_string(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        if isinstance(value := data.get(key), str):
            return value
    for value in data.values():
        if isinstance(value, dict) and (result := _find_string(value, *keys)) is not None:
            return result
    return None


def _kwh(value: float | None, unit: str | None) -> float | None:
    if value is None:
        return None
    factor = {"WH": 0.001, "KWH": 1, "MWH": 1000}.get((unit or "WH").upper(), 0.001)
    return round(value * factor, 3)


def _energy_total_kwh(data: dict[str, Any]) -> float | None:
    source = _mapping(data.get("production")) or data
    unit = _find_string(source, "units", "unit")
    if values := _find_list(source, "values"):
        source = values[-1]
    return _kwh(
        _find_number(source, "total", "energy", "value"),
        unit or _find_string(source, "units", "unit"),
    )


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is not None and parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.get_default_time_zone())
    return parsed
