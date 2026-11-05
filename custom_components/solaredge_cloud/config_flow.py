"""Config flow: enter the client credentials and grant access at SolarEdge.

SolarEdge does not return `state` on the callback, so Home Assistant's
standard OAuth2 flow can't be used. A dedicated callback view finds the pending
flow by site_id (or, if that is missing, the only pending flow).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from aiohttp import web
import voluptuous as vol

from homeassistant.components import http
from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import UnknownFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .api import (
    SolarEdgeError,
    SolarEdgeV2,
    build_authorize_url,
    generate_pkce,
    token_request,
)
from .const import (
    CALLBACK_PATH,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_SITE_ID,
    CONF_TOKEN,
    DEVELOPER_PORTAL_URL,
    DOMAIN,
    LOGGER,
)

DATA_PENDING = f"{DOMAIN}_pending_flows"
DATA_VIEW = f"{DOMAIN}_view_registered"


def _redirect_uri(hass: HomeAssistant) -> str:
    try:
        base = get_url(hass, allow_internal=False, prefer_external=True)
    except NoURLAvailableError:
        base = get_url(hass)
    return f"{base}{CALLBACK_PATH}"


def _ensure_view(hass: HomeAssistant) -> None:
    if not hass.data.get(DATA_VIEW):
        hass.http.register_view(SolarEdgeCallbackView())
        hass.data[DATA_VIEW] = True


class SolarEdgeCallbackView(http.HomeAssistantView):
    """Receives ?code=...&site_id=... from connect.solaredge.com."""

    requires_auth = False
    url = CALLBACK_PATH
    name = f"api:{DOMAIN}:callback"

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app[http.KEY_HASS]
        pending: dict[str, str] = hass.data.get(DATA_PENDING, {})
        site_id = request.query.get("site_id")
        flow_id = pending.get(site_id) if site_id else None
        if flow_id is None and len(pending) == 1:
            flow_id = next(iter(pending.values()))
        if flow_id is None:
            return _page("No pending SolarEdge setup found. Start the integration again in Home Assistant.", 400)

        user_input = {"site_id": site_id}
        if "code" in request.query:
            user_input["code"] = request.query["code"]
        else:
            user_input["error"] = request.query.get("error_description") or request.query.get("error", "unknown")
        try:
            result = await hass.config_entries.flow.async_configure(flow_id=flow_id, user_input=user_input)
        except UnknownFlow:
            return _page("This setup attempt has expired. Start again in Home Assistant.", 400)
        if result.get("step_id") == "auth_failed":
            return _page("Authorization failed; Home Assistant shows the reason.", 400)
        return web.Response(
            content_type="text/html",
            text="<p>Done, you can close this window.</p><script>window.close()</script>",
        )


def _page(text: str, status: int) -> web.Response:
    return web.Response(content_type="text/html", text=f"<p>{text}</p>", status=status)


class SolarEdgeCloudConfigFlow(ConfigFlow, domain=DOMAIN):
    """Steps: credentials → consent (external) → finish."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._verifier = ""
        self._redirect_uri = ""
        self._auth_error = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data = {
                CONF_SITE_ID: str(user_input[CONF_SITE_ID]).strip(),
                CONF_CLIENT_ID: user_input[CONF_CLIENT_ID].strip(),
                CONF_CLIENT_SECRET: user_input[CONF_CLIENT_SECRET].strip(),
            }
            if self.source != SOURCE_REAUTH:
                await self.async_set_unique_id(self._data[CONF_SITE_ID])
                self._abort_if_unique_id_configured()
            return await self.async_step_auth()

        defaults = self._data or {}
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SITE_ID, default=defaults.get(CONF_SITE_ID, "")): str,
                    vol.Required(CONF_CLIENT_ID, default=defaults.get(CONF_CLIENT_ID, "")): str,
                    vol.Required(CONF_CLIENT_SECRET): str,
                }
            ),
            description_placeholders={
                "redirect_uri": _redirect_uri(self.hass),
                "developer_portal_url": DEVELOPER_PORTAL_URL,
            },
            errors=errors,
        )

    async def async_step_auth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is None:
            _ensure_view(self.hass)
            self.hass.data.setdefault(DATA_PENDING, {})[self._data[CONF_SITE_ID]] = self.flow_id
            self._verifier, challenge = generate_pkce()
            self._redirect_uri = _redirect_uri(self.hass)
            return self.async_external_step(
                step_id="auth",
                url=build_authorize_url(self._data[CONF_CLIENT_ID], self._redirect_uri, challenge),
            )

        self.hass.data.get(DATA_PENDING, {}).pop(self._data[CONF_SITE_ID], None)
        if (cb_site := user_input.get("site_id")) and cb_site != self._data[CONF_SITE_ID]:
            LOGGER.warning("Access was granted for site %s instead of %s", cb_site, self._data[CONF_SITE_ID])
        if "code" not in user_input:
            self._auth_error = user_input.get("error", "no authorization code received")
            return self.async_external_step_done(next_step_id="auth_failed")
        try:
            self._data[CONF_TOKEN] = await token_request(
                async_get_clientsession(self.hass),
                self._data[CONF_CLIENT_ID],
                self._data[CONF_CLIENT_SECRET],
                {
                    "grant_type": "authorization_code",
                    "code": user_input["code"],
                    "redirect_uri": self._redirect_uri,
                    "code_verifier": self._verifier,
                },
            )
        except SolarEdgeError as err:
            LOGGER.error("Exchanging the authorization code failed: %s", err)
            self._auth_error = str(err)
            return self.async_external_step_done(next_step_id="auth_failed")
        return self.async_external_step_done(next_step_id="finish")

    async def async_step_auth_failed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_abort(
            reason="auth_failed", description_placeholders={"error": self._auth_error}
        )

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        api = SolarEdgeV2(async_get_clientsession(self.hass))
        try:
            details = await api.get(
                self._data[CONF_TOKEN]["access_token"], f"/sites/{self._data[CONF_SITE_ID]}"
            )
        except SolarEdgeError as err:
            self._auth_error = str(err)
            return await self.async_step_auth_failed()
        site = details.get("site", details) if isinstance(details, dict) else {}
        title = site.get("name") or f"SolarEdge {self._data[CONF_SITE_ID]}"

        if self.source == SOURCE_REAUTH:
            return self.async_update_reload_and_abort(self._get_reauth_entry(), data=self._data)
        return self.async_create_entry(title=title, data=self._data)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        self._data = {
            CONF_SITE_ID: entry_data[CONF_SITE_ID],
            CONF_CLIENT_ID: entry_data[CONF_CLIENT_ID],
        }
        return await self.async_step_user()
