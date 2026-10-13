"""Data update coordinator - two cloud requests per update."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RemoconApi, RemoconAuthError, RemoconError, RemoconRateLimited
from .const import CULTURE, DEFAULT_SCAN_INTERVAL, DOMAIN, MENU_IDS, CONF_SCAN_INTERVAL, data_item_request

_LOGGER = logging.getLogger(__name__)


@dataclass
class RemoconData:
    """One snapshot of the plant."""

    data_items: dict[str, dict[str, Any]]  # "<id>@<zone>" -> item
    menu_items: dict[int, dict[str, Any]]  # number -> item


type RemoconConfigEntry = ConfigEntry["RemoconCoordinator"]


class RemoconCoordinator(DataUpdateCoordinator[RemoconData]):
    """Polls the Remocon-Net cloud."""

    config_entry: RemoconConfigEntry

    def __init__(self, hass: HomeAssistant, entry: RemoconConfigEntry, api: RemoconApi, gateway: str) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {gateway}",
            update_interval=timedelta(seconds=interval),
        )
        self.api = api
        self.gateway = gateway
        self.features: dict[str, Any] | None = None
        self.plant: dict[str, Any] = {}

    @property
    def zones(self) -> list[int]:
        zones = (self.features or {}).get("zones") or [{"num": 1}]
        return [int(z.get("num", 1)) for z in zones]

    async def _async_setup(self) -> None:
        """Read static plant info once."""
        try:
            self.features = await self.api.get_features(self.gateway)
            plants = await self.api.get_plants()
        except RemoconAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except RemoconError as err:
            raise UpdateFailed(str(err)) from err
        self.plant = next((p for p in plants if p.get("gwId") == self.gateway), {})

    async def _async_update_data(self) -> RemoconData:
        try:
            data_items = await self.api.get_data_items(
                self.gateway, self.features or {}, data_item_request(self.zones), CULTURE
            )
            try:
                menu_items = await self.api.get_menu_items(self.gateway, MENU_IDS)
            except RemoconRateLimited:
                raise
            except RemoconAuthError:
                raise
            except RemoconError as err:
                # menuItems are fragile (one unsupported number -> HTTP 500); keep the last values
                _LOGGER.warning("Reading menuItems failed, keeping previous values: %s", err)
                menu_items = self.data.menu_items if self.data else {}
        except RemoconAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except RemoconRateLimited as err:
            raise UpdateFailed(f"Cloud rate limit (HTTP 429): {err}") from err
        except RemoconError as err:
            raise UpdateFailed(str(err)) from err
        return RemoconData(data_items=data_items, menu_items=menu_items)
