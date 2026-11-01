"""Import of the EM20 consumption into Home Assistant long-term statistics (usable in the Energy dashboard)."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMeanType, StatisticMetaData
from homeassistant.components.recorder.statistics import async_add_external_statistics, statistics_during_period
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .energy_values import TYPE_CH, TYPE_DHW, hourly_rows, window_start

_LOGGER = logging.getLogger(__name__)

# consumption type -> statistic id suffix
STATISTICS = {
    TYPE_CH: "ch_electricity",
    TYPE_DHW: "dhw_electricity",
}
# statistic names are stored in the recorder (not translatable by the frontend) -> Home Assistant language
STATISTIC_NAMES = {
    "cs": {TYPE_CH: "Tepelné čerpadlo – topení (elektřina)", TYPE_DHW: "Tepelné čerpadlo – teplá voda (elektřina)"},
    "de": {TYPE_CH: "Wärmepumpe – Heizung (Strom)", TYPE_DHW: "Wärmepumpe – Warmwasser (Strom)"},
    "en": {TYPE_CH: "Heat pump – heating (electricity)", TYPE_DHW: "Heat pump – hot water (electricity)"},
}
BASE_LOOKBACK = timedelta(days=60)  # how far back to look for the last known sum before the window


def statistic_id(gateway: str, kind: int) -> str:
    return f"{DOMAIN}:{gateway.lower()}_{STATISTICS[kind]}"


def statistic_name(language: str | None, kind: int) -> str:
    names = STATISTIC_NAMES.get((language or "").split("-")[0].lower(), STATISTIC_NAMES["en"])
    return names[kind]


async def _base_sum(hass: HomeAssistant, stat_id: str, start: datetime) -> float:
    """Cumulative sum of the last statistics row before `start` (0 when there is none).

    Always read from the recorder - never from a cache - so a restart cannot reset the series.
    """
    result = await get_instance(hass).async_add_executor_job(
        statistics_during_period, hass, start - BASE_LOOKBACK, start, {stat_id}, "hour", None, {"sum"}
    )
    rows = result.get(stat_id) or []
    return float(rows[-1].get("sum") or 0.0) if rows else 0.0


async def async_import_energy(
    hass: HomeAssistant, gateway: str, kind: int, buckets: list[float], bucket_end: datetime
) -> None:
    """(Re)write the hourly rows of the last 48 hours; same start timestamps are overwritten in place."""
    stat_id = statistic_id(gateway, kind)
    # alignment is decided in local time (last_bucket_end), but hour arithmetic must run in UTC:
    # "minus 48 h" on a zoneinfo datetime is wall-clock arithmetic and skips/duplicates an hour at DST
    bucket_end_utc = dt_util.as_utc(bucket_end)
    start = window_start(buckets, bucket_end_utc)
    base = await _base_sum(hass, stat_id, start)
    rows = hourly_rows(buckets, bucket_end_utc, base)
    metadata = StatisticMetaData(
        mean_type=StatisticMeanType.NONE,
        has_sum=True,
        name=statistic_name(hass.config.language, kind),
        source=DOMAIN,
        statistic_id=stat_id,
        unit_class="energy",
        unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    )
    stats = [StatisticData(start=r.start, state=r.state, sum=r.sum) for r in rows]
    _LOGGER.debug("Importing %s rows for %s from %s (base sum %s)", len(stats), stat_id, start, base)
    async_add_external_statistics(hass, metadata, stats)
