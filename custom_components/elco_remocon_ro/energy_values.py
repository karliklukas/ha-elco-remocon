"""Energy consumption reports (EM20 meter) - parsing and bucket/time logic, no Home Assistant imports.

consSequencesApi8 returns a list of {"k": consumption type, "p": period, "v": [values]}.
Verified on a GALEVO plant (probe 2026-10-13, values are ELECTRICITY in kWh):
  p=1 -> 24 buckets of 2 hours = the last 48 hours; the last bucket ends at the latest
         even hour (local time - see BUCKET_ALIGNMENT)
  p=2 -> the last 7 days (daily), ending yesterday
  p=3 -> daily values from the 1st day of the previous month until yesterday
  p=4 -> monthly values, the last one is the previous (completed) month
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

# consumption types (k)
TYPE_CH = 1  # central heating - total energy (electricity on GALEVO with EM20)
TYPE_DHW = 2  # domestic hot water - total energy
TYPE_COOLING = 3

PERIOD_BUCKETS = 1
PERIOD_WEEK = 2
PERIOD_DAYS = 3
PERIOD_MONTHS = 4

BUCKET_HOURS = 2
# The cloud aligns the 2-hour buckets to even hours. Observed in CEST (UTC+2) where local and UTC
# even hours coincide; assumed LOCAL time. Re-check after the switch to CET (25 Oct 2026) using the
# diagnostic sensor "Konec posledního úseku spotřeby".
BUCKET_ALIGNMENT = "local"
# right after a bucket boundary the cloud may not have shifted the series yet
SETTLE_MINUTES = 15


@dataclass(frozen=True)
class EnergyRow:
    """One hourly statistics row."""

    start: datetime  # aware, start of the hour
    state: float  # kWh consumed in this hour
    sum: float  # cumulative kWh


def index_sequences(data: Any) -> dict[tuple[int, int], list[float]]:
    """{(type, period): [values]} from a consSequencesApi8 response."""
    out: dict[tuple[int, int], list[float]] = {}
    for seq in data if isinstance(data, list) else []:
        if not isinstance(seq, dict):
            continue
        try:
            key = (int(seq["k"]), int(seq["p"]))
        except (KeyError, TypeError, ValueError):
            continue
        out[key] = [float(v or 0) for v in seq.get("v") or []]
    return out


def last_value(sequences: dict[tuple[int, int], list[float]], kind: int, period: int) -> float | None:
    values = sequences.get((kind, period))
    return values[-1] if values else None


def last_bucket_end(now_local: datetime) -> datetime:
    """End of the newest complete 2-hour bucket: now floored to an even hour (local time)."""
    floored = now_local.replace(minute=0, second=0, microsecond=0)
    return floored - timedelta(hours=floored.hour % BUCKET_HOURS)


def is_settled(now_local: datetime) -> bool:
    """False during the first minutes after a bucket boundary (series may not be shifted yet)."""
    return now_local - last_bucket_end(now_local) >= timedelta(minutes=SETTLE_MINUTES)


def hourly_rows(buckets: list[float], bucket_end: datetime, base_sum: float) -> list[EnergyRow]:
    """Split 2-hour buckets into hourly rows (half each) and accumulate the sum from base_sum.

    buckets[-1] covers <bucket_end - 2h, bucket_end).
    bucket_end must be in UTC (or a fixed-offset zone) - timedelta arithmetic on a zoneinfo datetime
    is wall-clock based and would skip/duplicate an hour at a DST switch.
    """
    rows: list[EnergyRow] = []
    total = base_sum
    first_start = bucket_end - timedelta(hours=BUCKET_HOURS * len(buckets))
    for i, value in enumerate(buckets):
        bucket_start = first_start + timedelta(hours=BUCKET_HOURS * i)
        part = value / BUCKET_HOURS
        for h in range(BUCKET_HOURS):
            total = round(total + part, 4)
            rows.append(EnergyRow(start=bucket_start + timedelta(hours=h), state=round(part, 4), sum=total))
    return rows


def window_start(buckets: list[float], bucket_end: datetime) -> datetime:
    return bucket_end - timedelta(hours=BUCKET_HOURS * len(buckets))
