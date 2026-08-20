"""Conservative async rate limiting for Telegram API calls."""

import asyncio
import time


class AsyncRateLimiter:
    def __init__(self, min_interval_seconds: float) -> None:
        self.min_interval_seconds = min_interval_seconds
        self._last_call_at = 0.0

    async def wait(self) -> None:
        elapsed = time.monotonic() - self._last_call_at
        remaining = self.min_interval_seconds - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)
        self._last_call_at = time.monotonic()
