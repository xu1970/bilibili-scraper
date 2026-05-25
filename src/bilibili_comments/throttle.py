"""Randomized delays between API requests."""

from __future__ import annotations

import asyncio
import random


def random_pause_seconds(base: float, *, jitter: float = 0.5) -> float:
    """
    Draw a pause duration around ``base``.

    With default ``jitter=0.5``, returns a value uniformly distributed in
    ``[base * 0.5, base * 1.5]``.
    """
    if base <= 0:
        return 0.0
    low = base * (1.0 - jitter)
    high = base * (1.0 + jitter)
    return random.uniform(max(0.0, low), high)


async def random_sleep(base: float, *, jitter: float = 0.5) -> None:
    """``asyncio.sleep`` for a randomized duration derived from ``base``."""
    seconds = random_pause_seconds(base, jitter=jitter)
    if seconds > 0:
        await asyncio.sleep(seconds)
