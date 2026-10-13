"""Minimal read-only client for the Remocon-Net (Ariston) cloud API.

The client never writes to the device. It only:
  * logs in (accounts/login) and keeps the token,
  * lists plants and reads plant features,
  * reads dataItems (named values) and menuItems (numbered service parameters).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

DEFAULT_API_URL = "https://www.remocon-net.remotethermo.com/api/v2/"
USER_AGENT = "RestSharp/106.11.7.0"  # the official app's client identifier, same as fustom/ariston
TIMEOUT = aiohttp.ClientTimeout(total=30)
RETRY_DELAY = 3  # seconds before the single retry after a server error


class RemoconError(Exception):
    """Generic API error."""


class RemoconAuthError(RemoconError):
    """Login rejected (wrong e-mail / password)."""


class RemoconRateLimited(RemoconError):
    """Cloud answered HTTP 429."""


class RemoconApi:
    """Read-only Remocon-Net API client."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        api_url: str = DEFAULT_API_URL,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._api_url = api_url if api_url.endswith("/") else api_url + "/"
        self._token: str | None = None

    async def login(self) -> None:
        """Get a new auth token."""
        status, data = await self._raw("POST", "accounts/login", {"usr": self._username, "pwd": self._password}, auth=False)
        if status in (400, 401, 403, 405) or (status == 200 and not (isinstance(data, dict) and data.get("token"))):
            raise RemoconAuthError(f"Login failed (HTTP {status})")
        if status != 200:
            raise RemoconError(f"Login failed (HTTP {status})")
        self._token = data["token"]

    async def _raw(self, method: str, path: str, body: Any = None, auth: bool = True) -> tuple[int, Any]:
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if auth and self._token:
            headers["ar.authToken"] = self._token
        try:
            async with self._session.request(
                method, self._api_url + path, json=body, headers=headers, timeout=TIMEOUT
            ) as resp:
                text = await resp.text()
                if resp.status == 429:
                    raise RemoconRateLimited(text[:200])
                data: Any = None
                if text:
                    try:
                        data = await resp.json(content_type=None)
                    except ValueError:
                        data = text
                return resp.status, data
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise RemoconError(f"Connection error: {err}") from err

    async def _request(self, method: str, path: str, body: Any = None) -> Any:
        """Authenticated request; logs in once more when the token expired."""
        if self._token is None:
            await self.login()
        status, data = await self._raw(method, path, body)
        if status in (401, 405):  # expired token
            _LOGGER.debug("Token rejected (HTTP %s), logging in again", status)
            await self.login()
            status, data = await self._raw(method, path, body)
        elif status >= 500:  # e.g. "Gateway error ... InternalError" - the gateway is often just busy
            _LOGGER.debug("HTTP %s from %s, retrying once in %ss", status, path.split("?")[0], RETRY_DELAY)
            await asyncio.sleep(RETRY_DELAY)
            status, data = await self._raw(method, path, body)
        if status != 200:
            raise RemoconError(f"{method} {path.split('?')[0]} failed (HTTP {status}): {str(data)[:200]}")
        return data

    async def get_plants(self) -> list[dict[str, Any]]:
        """Return plants of the account (gwId, plantName, gwFwVer, ...)."""
        data = await self._request("GET", "remote/plants/lite")
        return data if isinstance(data, list) else []

    async def get_features(self, gateway: str) -> dict[str, Any]:
        data = await self._request("GET", f"remote/plants/{gateway}/features")
        if not isinstance(data, dict):
            raise RemoconError("Unexpected features response")
        return data

    async def get_data_items(
        self, gateway: str, features: dict[str, Any], items: list[dict[str, Any]], culture: str
    ) -> dict[str, dict[str, Any]]:
        """Read named values. Unknown IDs are silently ignored by the cloud.

        Returns {"<id>@<zone>": item}.
        """
        data = await self._request(
            "POST",
            f"remote/dataItems/{gateway}/get?umsys=si",
            {"useCache": False, "items": items, "features": features, "culture": culture},
        )
        return index_data_items(data)

    async def get_consumption_sequences(self, gateway: str) -> Any:
        """Energy consumption report series (EM20 meter) for heating, hot water and cooling."""
        return await self._request("GET", f"remote/reports/{gateway}/consSequencesApi8?usages=Ch%2CDhw%2CCooling")

    async def get_menu_items(self, gateway: str, ids: list[int]) -> dict[int, dict[str, Any]]:
        """Read numbered service parameters.

        WARNING: a single unsupported ID makes the cloud fail the whole request (HTTP 500),
        so only IDs verified for the plant may be requested.
        """
        data = await self._request("GET", f"menuItems/{gateway}?menuItems={','.join(map(str, ids))}")
        return index_menu_items(data)


def index_data_items(data: Any) -> dict[str, dict[str, Any]]:
    """Index a dataItems response by "<id>@<zone>"."""
    items = data.get("items") if isinstance(data, dict) else None
    out: dict[str, dict[str, Any]] = {}
    for item in items or []:
        if not isinstance(item, dict) or "id" not in item:
            continue
        out[f"{item['id']}@{item.get('zone', item.get('zn', 0))}"] = item
    return out


def index_menu_items(data: Any) -> dict[int, dict[str, Any]]:
    """Index a menuItems response by numeric id."""
    out: dict[int, dict[str, Any]] = {}
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict) and "id" in item:
            try:
                out[int(item["id"])] = item
            except (TypeError, ValueError):
                continue
    return out


def item_text(item: dict[str, Any]) -> str | None:
    """Human text of an enum value (dataItems optTexts or menuItems options dict)."""
    value = item.get("value")
    if value is None:
        return None
    options = item.get("options")
    texts = item.get("optTexts")
    if isinstance(options, list) and isinstance(texts, list):  # dataItems
        for opt, txt in zip(options, texts):
            if opt == value:
                return txt
        return None
    if isinstance(options, dict):  # menuItems: {"0": "OFF", ...}
        return options.get(str(int(value)))
    return None
