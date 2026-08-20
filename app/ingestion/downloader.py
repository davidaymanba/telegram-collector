"""Safe Telegram media downloading."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.storage.paths import ensure_child_path, incoming_file_path


@dataclass(frozen=True)
class DownloadedFile:
    path: Path
    size_bytes: int


async def download_message_media(
    message: object,
    *,
    incoming_root: Path,
    channel_name: str,
    message_id: int,
    filename: str,
) -> DownloadedFile:
    """Download Telegram media atomically into incoming storage."""

    final_path = incoming_file_path(incoming_root, channel_name, message_id, filename)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    ensure_child_path(incoming_root, final_path)

    temp_path = final_path.with_name(f".{final_path.name}.{uuid4().hex}.part")
    downloaded_path = await message.download_media(file=str(temp_path))
    actual_temp_path = Path(downloaded_path) if downloaded_path else temp_path

    if not actual_temp_path.exists() or actual_temp_path.stat().st_size == 0:
        raise RuntimeError("Telegram media download produced an empty file")

    os.replace(actual_temp_path, final_path)
    return DownloadedFile(path=final_path, size_bytes=final_path.stat().st_size)
