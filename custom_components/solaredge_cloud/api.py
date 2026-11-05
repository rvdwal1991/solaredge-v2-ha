"""Small client for the SolarEdge Monitoring API V2 (OAuth2 + PKCE)."""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from typing import Any
from urllib.parse import urlencode

from aiohttp import ClientError, ClientSession

from .const import API_BASE_URL, LOGGER, OAUTH2_AUTHORIZE, OAUTH2_SCOPE, OAUTH2_TOKEN


class SolarEdgeError(Exception):
    """Generic API error."""


class SolarEdgeAuthError(SolarEdgeError):
    """Token rejected or expired: re-authorization needed."""


class SolarEdgeRateLimitError(SolarEdgeError):
    """Per-minute or monthly limit reached."""


class SolarEdgeNotFoundError(SolarEdgeError):
    """Endpoint not available for this site."""


def generate_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge)."""
    verifier = secrets.token_urlsafe(96)[:128]
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def build_authorize_url(client_id: str, redirect_uri: str, challenge: str) -> str:
    """Build the URL where the user grants access."""
    return f"{OAUTH2_AUTHORIZE}?" + urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": OAUTH2_SCOPE,
            "access_duration": "24",
            "state": secrets.token_urlsafe(),
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )


async def token_request(
    session: ClientSession, client_id: str, client_secret: str, data: dict[str, str]
) -> dict[str, Any]:
    """Request a token.

    Known implementations use two variants (JSON with the client credentials in
    the body, or form-encoded with Basic auth). Try JSON first and fall back to
    the form variant on a 4xx.
    """
    attempts = (
        {"json": {**data, "client_id": client_id, "client_secret": client_secret}},
        {
            "data": data,
            "headers": {
                "Authorization": "Basic "
                + base64.b64encode(f"{client_id}:{client_secret}".encode()).decode(),
                "Accept": "application/json",
            },
        },
    )
    last_error = ""
    for kwargs in attempts:
        try:
            async with session.post(OAUTH2_TOKEN, **kwargs) as resp:
                body = await resp.json(content_type=None)
                if resp.status < 400 and isinstance(body, dict) and body.get("access_token"):
                    body["expires_at"] = time.time() + float(body.get("expires_in", 7200))
                    return body
                last_error = f"{resp.status}: {body}"
                LOGGER.debug("Token request failed (%s)", last_error)
                if resp.status >= 500:
                    raise SolarEdgeError(f"Token server returned {last_error}")
        except (ClientError, ValueError) as err:
            raise SolarEdgeError(f"Token request failed: {err}") from err
    raise SolarEdgeAuthError(f"Token rejected ({last_error})")


class SolarEdgeV2:
    """Authenticated GET requests against the V2 API."""

    def __init__(self, session: ClientSession) -> None:
        self._session = session
        self.rate_limit: dict[str, str] = {}

    async def get(
        self, access_token: str, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        try:
            async with self._session.get(
                f"{API_BASE_URL}{path}",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                params=params,
            ) as resp:
                self.rate_limit = {
                    k.lower(): v for k, v in resp.headers.items() if k.lower().startswith("x-ratelimit")
                }
                if resp.status in (401, 403):
                    raise SolarEdgeAuthError(f"{path}: {resp.status}")
                if resp.status == 404:
                    raise SolarEdgeNotFoundError(path)
                if resp.status == 429:
                    raise SolarEdgeRateLimitError(
                        f"{path}: limit reached ({await resp.text()})"
                    )
                if resp.status >= 400:
                    raise SolarEdgeError(f"{path}: {resp.status} {await resp.text()}")
                return await resp.json(content_type=None)
        except ClientError as err:
            raise SolarEdgeError(f"{path}: {err}") from err
