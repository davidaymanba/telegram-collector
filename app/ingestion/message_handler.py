"""Telegram message metadata extraction."""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TelegramMessageSnapshot:
    telegram_message_id: int
    message_date: datetime | None
    caption: str | None
    media_type: str | None
    file_name: str | None
    file_size: int | None
    mime_type: str | None
    extension: str | None
    has_media: bool
    is_supported_media: bool
    telegram_metadata: dict[str, Any]


def _infer_extension(file_name: str | None, mime_type: str | None) -> str | None:
    if file_name:
        suffix = Path(file_name).suffix.lower()
        if suffix:
            return suffix
    if mime_type:
        return mimetypes.guess_extension(mime_type)
    return None


def _media_type(message: Any, mime_type: str | None) -> str | None:
    if getattr(message, "photo", None) is not None:
        return "photo"
    if getattr(message, "document", None) is not None:
        return "document"
    if mime_type:
        return mime_type.split("/", maxsplit=1)[0]
    if getattr(message, "media", None) is not None:
        return type(message.media).__name__
    return None


def snapshot_message(
    message: Any, supported_extensions: tuple[str, ...]
) -> TelegramMessageSnapshot:
    """Extract stable metadata from a Telethon message or a test double."""

    file_obj = getattr(message, "file", None)
    file_name = getattr(file_obj, "name", None)
    file_size = getattr(file_obj, "size", None)
    mime_type = getattr(file_obj, "mime_type", None)
    extension = _infer_extension(file_name, mime_type)
    media_type = _media_type(message, mime_type)
    has_media = getattr(message, "media", None) is not None or file_obj is not None
    text = getattr(message, "message", None) or getattr(message, "text", None)

    if file_name is None and has_media:
        fallback_extension = extension or ""
        file_name = f"telegram_message_{message.id}{fallback_extension}"

    return TelegramMessageSnapshot(
        telegram_message_id=int(message.id),
        message_date=getattr(message, "date", None),
        caption=text,
        media_type=media_type,
        file_name=file_name,
        file_size=file_size,
        mime_type=mime_type,
        extension=extension,
        has_media=has_media,
        is_supported_media=bool(extension and extension.lower() in supported_extensions),
        telegram_metadata={
            "mime_type": mime_type,
            "extension": extension,
            "grouped_id": getattr(message, "grouped_id", None),
        },
    )
