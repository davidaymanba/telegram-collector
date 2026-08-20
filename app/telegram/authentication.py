"""Interactive one-time Telegram authentication."""

from __future__ import annotations

import getpass
import logging

from telethon.errors import SessionPasswordNeededError

from app.config.settings import Settings
from app.telegram.client import build_telegram_client, protect_session_path

logger = logging.getLogger(__name__)


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
