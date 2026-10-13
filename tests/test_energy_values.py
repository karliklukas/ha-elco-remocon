"""Bucket/time logic of the EM20 consumption reports (series from a real plant, two probes 77 min apart)."""

from datetime import datetime, timedelta, timezone
import importlib
from zoneinfo import ZoneInfo

from conftest import PKG

ev = importlib.import_module(f"{PKG}.energy_values")

CEST = timezone(timedelta(hours=2))
# probe 1 at 12:45 CEST, probe 2 at 14:02 CEST - the series shifted by exactly one 2-hour bucket
DHW_1245 = [0.0] * 9 + [0.658, 1.063] + [0.0] * 11 + [1.866, 0.0]
DHW_1402 = [0.0] * 8 + [0.658, 1.063] + [0.0] * 11 + [1.866, 0.0, 0.0]
CH_1402 = [0.0] * 21 + [2.466, 3.808, 0.08]
RESPONSE = [
    {"k": 1, "p": 1, "v": CH_1402},
    {"k": 2, "p": 1, "v": DHW_1402},
    {"k": 2, "p": 3, "v": [2.588, 1.286, 1.722]},
    {"k": 2, "p": 4, "v": [0.0, 46.422, 54.841]},
    {"k": "bad"},
]


def test_index_and_last_values():
    seq = ev.index_sequences(RESPONSE)
    assert seq[(1, 1)] == CH_1402
    assert ev.last_value(seq, ev.TYPE_DHW, ev.PERIOD_DAYS) == 1.722  # yesterday
    assert ev.last_value(seq, ev.TYPE_DHW, ev.PERIOD_MONTHS) == 54.841  # previous month
    assert ev.last_value(seq, ev.TYPE_COOLING, ev.PERIOD_DAYS) is None


def test_last_bucket_end_even_hours():
    assert ev.last_bucket_end(datetime(2026, 10, 13, 14, 2, tzinfo=CEST)) == datetime(2026, 10, 13, 14, 0, tzinfo=CEST)
    assert ev.last_bucket_end(datetime(2026, 10, 13, 12, 45, tzinfo=CEST)) == datetime(2026, 10, 13, 12, 0, tzinfo=CEST)
    assert ev.last_bucket_end(datetime(2026, 10, 13, 13, 59, tzinfo=CEST)) == datetime(2026, 10, 13, 12, 0, tzinfo=CEST)


def test_settle_window():
    assert not ev.is_settled(datetime(2026, 10, 13, 14, 5, tzinfo=CEST))
    assert ev.is_settled(datetime(2026, 10, 13, 14, 20, tzinfo=CEST))


def test_both_probes_map_dhw_to_the_same_hours():
    """Yesterday's DHW heating (06-10 h) must land on the same hours from both probes."""
    def nonzero(buckets, now):
        rows = ev.hourly_rows(buckets, ev.last_bucket_end(now), 0.0)
        return {r.start: r.state for r in rows if r.state}
    a = nonzero(DHW_1245, datetime(2026, 10, 13, 12, 45, tzinfo=CEST))
    b = nonzero(DHW_1402, datetime(2026, 10, 13, 14, 2, tzinfo=CEST))
    assert a == b
    hours = sorted(a)
    assert hours[0] == datetime(2026, 10, 12, 6, 0, tzinfo=CEST)  # 0.658 kWh in 06-08 h yesterday
    assert hours[-1] == datetime(2026, 10, 13, 9, 0, tzinfo=CEST)  # 1.866 kWh in 08-10 h today


def test_dst_switch_has_no_gap_or_overlap():
    """48 real hours across the CEST->CET switch (25 Oct 2026) - computed in UTC as energy_stats does."""
    prague = ZoneInfo("Europe/Prague")
    now = datetime(2026, 10, 26, 14, 20, tzinfo=prague)  # winter time
    end_local = ev.last_bucket_end(now)
    assert (end_local.hour, end_local.tzinfo) == (14, prague)  # alignment stays on even LOCAL hours
    end_utc = end_local.astimezone(timezone.utc)
    rows = ev.hourly_rows([1.0] * 24, end_utc, 0.0)
    gaps = {(b.start - a.start).total_seconds() for a, b in zip(rows, rows[1:])}
    assert gaps == {3600.0}
    assert rows[-1].start - rows[0].start == timedelta(hours=47)
    assert end_utc - rows[0].start == timedelta(hours=48)


def test_hourly_rows_sum_and_shape():
    end = datetime(2026, 10, 13, 14, 0, tzinfo=CEST)
    rows = ev.hourly_rows(DHW_1402, end, base_sum=100.0)
    assert len(rows) == 48
    assert rows[0].start == datetime(2026, 10, 11, 14, 0, tzinfo=CEST) == ev.window_start(DHW_1402, end)
    assert rows[-1].start == datetime(2026, 10, 13, 13, 0, tzinfo=CEST)
    assert round(rows[-1].sum - 100.0, 3) == 3.587  # yesterday 1.722 + today 1.866
    assert all(b.sum >= a.sum for a, b in zip(rows, rows[1:]))
