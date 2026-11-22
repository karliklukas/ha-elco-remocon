"""Polling backoff after HTTP 429 (Requests are blocked)."""

import importlib

import conftest  # noqa: F401  (registers the package without Home Assistant)

backoff = importlib.import_module(f"{conftest.PKG}.backoff")


def test_doubles_up_to_max():
    b = backoff.Backoff()
    factors = []
    for _ in range(5):
        b.rate_limited()
        factors.append(b.factor)
    assert factors == [2, 4, 8, 8, 8]


def test_steps_down_only_after_a_run_of_good_polls():
    b = backoff.Backoff()
    b.rate_limited()
    b.rate_limited()  # 4x
    for _ in range(backoff.RECOVERY_POLLS - 1):
        b.success()
    assert b.factor == 4
    b.success()
    assert b.factor == 2
    for _ in range(backoff.RECOVERY_POLLS):
        b.success()
    assert b.factor == 1


def test_a_429_during_recovery_restarts_the_count():
    b = backoff.Backoff()
    b.rate_limited()  # 2x
    for _ in range(backoff.RECOVERY_POLLS - 1):
        b.success()
    b.rate_limited()  # 4x, count restarts
    for _ in range(backoff.RECOVERY_POLLS - 1):
        b.success()
    assert b.factor == 4


def test_success_without_backoff_does_nothing():
    b = backoff.Backoff()
    for _ in range(50):
        b.success()
    assert (b.factor, b.good_polls) == (1, 0)
