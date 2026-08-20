"""Small retry helpers for transient failures."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    backoff_factor: float = 2.0


async def retry_async[T](
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy | None = None,
    retryable_exceptions: tuple[type[BaseException], ...] = (TimeoutError, ConnectionError),
) -> T:
    policy = policy or RetryPolicy()
    attempt = 0
    delay = policy.initial_delay_seconds
    while True:
        attempt += 1
        try:
            return await operation()
        except retryable_exceptions:
            if attempt >= policy.max_attempts:
                raise
            await asyncio.sleep(delay)
            delay *= policy.backoff_factor
