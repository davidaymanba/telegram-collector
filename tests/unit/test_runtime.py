import asyncio
from pathlib import Path

import pytest

from app.runtime.locking import LockAlreadyHeldError, file_lock
from app.runtime.retry import RetryPolicy, retry_async
from app.telegram.floodwait import flood_wait_seconds, run_with_floodwait_retry


def test_file_lock_prevents_overlapping_runs(tmp_path: Path) -> None:
    lock_path = tmp_path / "collector.lock"
    with file_lock(lock_path):
        with pytest.raises(LockAlreadyHeldError):
            with file_lock(lock_path):
                pass


def test_retry_async_retries_transient_failure() -> None:
    attempts = 0

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError("temporary")
        return "ok"

    result = asyncio.run(
        retry_async(operation, policy=RetryPolicy(max_attempts=2, initial_delay_seconds=0))
    )

    assert result == "ok"
    assert attempts == 2


def test_flood_wait_seconds_accepts_telethon_like_error() -> None:
    FakeFloodWaitError = type("FloodWaitError", (Exception,), {})
    exc = FakeFloodWaitError("wait")
    exc.seconds = 4

    assert flood_wait_seconds(exc) == 4


def test_run_with_floodwait_retry_waits_and_retries(monkeypatch) -> None:
    calls = 0
    sleeps: list[int] = []
    FakeFloodWaitError = type("FloodWaitError", (Exception,), {})

    async def fake_sleep(seconds: int) -> None:
        sleeps.append(seconds)

    async def operation() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            exc = FakeFloodWaitError("wait")
            exc.seconds = 2
            raise exc
        return "ok"

    monkeypatch.setattr("app.telegram.floodwait.asyncio.sleep", fake_sleep)

    assert asyncio.run(run_with_floodwait_retry(operation, max_attempts=2)) == "ok"
    assert sleeps == [2]

