"""File locking to prevent overlapping cron runs."""

from __future__ import annotations

import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO


class LockAlreadyHeldError(RuntimeError):
    pass


@contextmanager
def file_lock(lock_path: Path) -> Iterator[None]:
    """Acquire an exclusive non-blocking lock for the current process."""

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file: TextIO = lock_path.open("w", encoding="utf-8")
    try:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LockAlreadyHeldError(f"Lock already held: {lock_path}") from exc
        lock_file.write(str(lock_path))
        lock_file.flush()
        yield
    finally:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            lock_file.close()
