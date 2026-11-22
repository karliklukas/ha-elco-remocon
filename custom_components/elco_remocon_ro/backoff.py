"""Polling backoff when the cloud rate limits the account (HTTP 429) - no Home Assistant imports.

Since 2026-11 the Remocon-Net cloud answers "429 Requests are blocked" when an account sends a bit
more requests than it allows (seen as one blocked poll out of five at 2 requests / 120 s). Going
back to the full rate right after the first good poll would hit the limit again a few minutes
later, so the interval steps down only after a run of good polls.
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_FACTOR = 8  # longest interval = 8x the configured one
RECOVERY_POLLS = 10  # good polls in a row before the interval is halved again


@dataclass
class Backoff:
    """Multiplier of the configured update interval."""

    factor: int = 1
    good_polls: int = 0

    def rate_limited(self) -> None:
        """The cloud answered 429: double the interval (up to MAX_FACTOR)."""
        self.factor = min(self.factor * 2, MAX_FACTOR)
        self.good_polls = 0

    def success(self) -> None:
        """A poll without 429: after RECOVERY_POLLS of them halve the interval."""
        if self.factor == 1:
            return
        self.good_polls += 1
        if self.good_polls >= RECOVERY_POLLS:
            self.factor //= 2
            self.good_polls = 0
