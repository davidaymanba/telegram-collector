"""Telegram FloodWait handling."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from telethon.errors import FloodWaitError

logger = logging.getLogger(__name__)


def flood_wait_seconds(exc: BaseException) -> int | None:
    if isinstance(exc, FloodWaitError):
        return int(exc.seconds)
    seconds = getattr(exc, "seconds", None)
    if exc.__class__.__name__ == "FloodWaitError" and seconds is not None:
        return int(seconds)
    return None


async def run_with_floodwait_retry[T](
    operation: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
) -> T:
    """Run an async Telegram operation and sleep when Telegram requests FloodWait."""

    attempts = 0
    while True:
        attempts += 1
        try:
            return await operation()
        except BaseException as exc:
            wait_seconds = flood_wait_seconds(exc)
            if wait_seconds is None or attempts >= max_attempts:
                raise
            logger.warning("Telegram FloodWait received", extra={"wait_seconds": wait_seconds})
            await asyncio.sleep(wait_seconds)
