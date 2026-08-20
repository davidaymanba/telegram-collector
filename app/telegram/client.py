"""Telethon client construction and Telegram session file protection."""

from __future__ import annotations

import os
from pathlib import Path

from telethon import TelegramClient

from app.config.settings import Settings


def protect_session_path(session_path: Path) -> None:
    """Create the session directory securely and restrict an existing session file."""

    session_path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(session_path.parent, 0o700)
    if session_path.exists():
        os.chmod(session_path, 0o600)


def build_telegram_client(settings: Settings) -> TelegramClient:
    """Build a Telethon client using configured credentials."""

    settings.require_telegram_credentials()
    protect_session_path(settings.telegram_session_path)
    api_hash = settings.telegram_api_hash.get_secret_value() if settings.telegram_api_hash else ""
    return TelegramClient(
        str(settings.telegram_session_path),
        settings.telegram_api_id,
        api_hash,
    )
