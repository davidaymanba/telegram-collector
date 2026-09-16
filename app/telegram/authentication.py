"""Interactive one-time Telegram authentication."""

from __future__ import annotations

import getpass
import logging
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable

from telethon.errors import SessionPasswordNeededError

from app.config.settings import Settings
from app.telegram.client import build_telegram_client, protect_session_path

logger = logging.getLogger(__name__)


class TelegramLoginError(ValueError):
    """Raised when the web login flow cannot continue."""


@dataclass
class _PendingLogin:
    phone: str
    phone_code_hash: str


_pending_login: _PendingLogin | None = None
_pending_login_lock = Lock()


def _clear_pending_login() -> None:
    global _pending_login
    with _pending_login_lock:
        _pending_login = None


async def web_login_start(
    settings: Settings,
    phone: str,
    *,
    client_factory: Callable[[Settings], Any] = build_telegram_client,
) -> dict[str, str]:
    """Request an OTP without storing the phone number or code on disk."""

    normalized_phone = phone.strip()
    if not normalized_phone:
        raise TelegramLoginError("Phone number is required")

    client = client_factory(settings)
    await client.connect()
    try:
        if await client.is_user_authorized():
            return {"status": "authorized"}
        sent_code = await client.send_code_request(normalized_phone)
        phone_code_hash = getattr(sent_code, "phone_code_hash", None)
        if not phone_code_hash:
            raise TelegramLoginError("Telegram did not return a verification code")
        global _pending_login
        with _pending_login_lock:
            _pending_login = _PendingLogin(normalized_phone, phone_code_hash)
        return {"status": "code_required"}
    finally:
        await client.disconnect()


async def web_login_verify(
    settings: Settings,
    code: str,
    password: str | None = None,
    *,
    client_factory: Callable[[Settings], Any] = build_telegram_client,
) -> dict[str, str]:
    """Verify the OTP, or complete Telegram two-factor authentication."""

    with _pending_login_lock:
        pending = _pending_login
    if pending is None:
        raise TelegramLoginError("Start Telegram login before verifying the code")

    client = client_factory(settings)
    await client.connect()
    try:
        try:
            await client.sign_in(
                phone=pending.phone,
                code=code.strip(),
                phone_code_hash=pending.phone_code_hash,
            )
        except SessionPasswordNeededError:
            if not password or not password.strip():
                return {"status": "password_required"}
            await client.sign_in(password=password)
        protect_session_path(settings.telegram_session_path)
        _clear_pending_login()
        return {"status": "authorized"}
    finally:
        await client.disconnect()


async def interactive_login(settings: Settings) -> None:
    """Run the one-time MTProto login flow and persist the Telethon session."""

    client = build_telegram_client(settings)
    await client.connect()
    try:
        if await client.is_user_authorized():
            logger.info("Telegram session is already authorized")
            return

        phone = input("Phone number (international format): ").strip()
        await client.send_code_request(phone)
        code = getpass.getpass("Telegram OTP code: ").strip()

        try:
            await client.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            password = getpass.getpass("Telegram 2FA password: ")
            await client.sign_in(password=password)

        protect_session_path(settings.telegram_session_path)
        logger.info("Telegram login completed")
    finally:
        await client.disconnect()
