"""Data update coordinator - two cloud requests per update."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import RemoconApi, RemoconAuthError, RemoconError, RemoconRateLimited
from .const import (
    CONF_SCAN_INTERVAL,
    CULTURE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    ENERGY_SCAN_INTERVAL,
    MENU_IDS,
    data_item_request,
)
from .energy_stats import async_import_energy
from .energy_values import (
    PERIOD_BUCKETS,
    SETTLE_MINUTES,
    TYPE_CH,
    TYPE_DHW,
    index_sequences,
    is_settled,
    last_bucket_end,
)

_LOGGER = logging.getLogger(__name__)

MAX_TOLERATED_FAILURES = 3  # failed polls in a row that still show the previous values (~6 min at 120 s)


@dataclass
class RemoconData:
    """One snapshot of the plant."""

    data_items: dict[str, dict[str, Any]]  # "<id>@<zone>" -> item
    menu_items: dict[int, dict[str, Any]]  # number -> item


@dataclass
class EnergyData:
    """EM20 consumption reports."""

    sequences: dict[tuple[int, int], list[float]]  # (type, period) -> values
    bucket_end: datetime  # end of the newest 2-hour bucket (local time)
    imported: bool  # statistics written in this update


type RemoconConfigEntry = ConfigEntry["RemoconCoordinator"]


class RemoconEnergyCoordinator(DataUpdateCoordinator[EnergyData]):
    """Polls the consumption reports (they change every 2 hours) and imports them into statistics."""

    def __init__(self, hass: HomeAssistant, entry: RemoconConfigEntry, api: RemoconApi, gateway: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {gateway} energy",
            update_interval=timedelta(seconds=ENERGY_SCAN_INTERVAL),
        )
        self.api = api
        self.gateway = gateway

    async def _async_update_data(self) -> EnergyData:
        try:
            raw = await self.api.get_consumption_sequences(self.gateway)
        except RemoconAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except RemoconError as err:
            if self.data is not None:
                _LOGGER.warning("Reading consumption failed, keeping previous values: %s", err)
                return self.data
            raise UpdateFailed(str(err)) from err
        sequences = index_sequences(raw)
        now = dt_util.now()
        bucket_end = last_bucket_end(now)
        imported = False
        if is_settled(now):
            for kind in (TYPE_CH, TYPE_DHW):
                buckets = sequences.get((kind, PERIOD_BUCKETS))
                if buckets:
                    await async_import_energy(self.hass, self.gateway, kind, buckets, bucket_end)
                    imported = True
        else:
            _LOGGER.debug("Within %s min after a bucket boundary, statistics import postponed", SETTLE_MINUTES)
        return EnergyData(sequences=sequences, bucket_end=bucket_end, imported=imported)


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
        self._failures = 0  # consecutive failed updates
        self.energy: RemoconEnergyCoordinator | None = None  # set in __init__.py when the plant has metering

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
            # the gateway sometimes fails a single read ("Gateway error ... InternalError");
            # keep showing the last values for a few polls instead of making everything unavailable
            self._failures += 1
            if self.data is not None and self._failures <= MAX_TOLERATED_FAILURES:
                _LOGGER.warning(
                    "Update failed (%s/%s), keeping previous values: %s", self._failures, MAX_TOLERATED_FAILURES, err
                )
                return self.data
            raise UpdateFailed(str(err)) from err
        self._failures = 0
        return RemoconData(data_items=data_items, menu_items=menu_items)
