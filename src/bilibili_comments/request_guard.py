"""HTTP configuration and retry helpers for bilibili_api requests."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from bilibili_api import settings as bili_settings
from bilibili_api.exceptions import ApiException, ResponseCodeException

REQUEST_TIMEOUT_SECONDS = 30.0

T = TypeVar("T")


def configure_http_timeouts(seconds: float = REQUEST_TIMEOUT_SECONDS) -> None:
    """
    Set bilibili_api's native HTTP timeout (aiohttp/httpx).

    No external ``asyncio.wait_for`` is applied — the library owns the socket timeout.
    """
    bili_settings.timeout = seconds


async def call_with_retry(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    label: str = "request",
    retries: int = 3,
    retry_delay: float = 2.0,
) -> T:
    """
    Await ``coro_factory`` with limited retries on API errors.

    Relies on ``bilibili_api.settings.timeout`` for per-request timeouts.
    """
    last_exc: BaseException | None = None
    for attempt in range(retries):
        try:
            return await coro_factory()
        except (ResponseCodeException, ApiException) as exc:
            last_exc = exc
            print(
                f"  WARNING: {label} failed ({exc}) "
                f"(attempt {attempt + 1}/{retries})",
                flush=True,
            )
            if attempt < retries - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))
    raise last_exc  # type: ignore[misc]
