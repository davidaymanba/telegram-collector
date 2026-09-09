"""Incremental Telegram channel collector."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import sessionmaker
from telethon import utils

from app.config.loaders import load_channels_config
from app.config.settings import Settings
from app.database.repositories.channels import ChannelRepository
from app.database.repositories.files import FileRepository
from app.database.repositories.messages import MessageRepository
from app.database.statuses import FileStatus
from app.ingestion.deduplication import Deduplicator
from app.ingestion.downloader import download_message_media
from app.ingestion.hashing import sha256_file
from app.ingestion.message_handler import TelegramMessageSnapshot, snapshot_message
from app.telegram.client import build_telegram_client
from app.telegram.floodwait import run_with_floodwait_retry
from app.telegram.rate_limiter import AsyncRateLimiter

logger = logging.getLogger(__name__)


@dataclass
class CollectionSummary:
    new_messages: int = 0
    downloaded_files: int = 0
    duplicate_files: int = 0
    unsupported_files: int = 0
    skipped_messages: int = 0
    failed_messages: int = 0


class TelegramSessionNotAuthorizedError(Exception):
    pass


class TelegramCollector:
    """Collect new messages and files from configured Telegram channels."""

    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker,
        telegram_client: Any | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.telegram_client = telegram_client
        self.rate_limiter = AsyncRateLimiter(settings.telegram_request_delay_seconds)

    async def collect(
        self,
        *,
        channel_name: str | None = None,
        limit: int | None = None,
    ) -> CollectionSummary:
        channels_config = load_channels_config(self.settings.channels_config_path)
        enabled_channels = channels_config.enabled_channels
        if channel_name is not None:
            requested_channel = channel_name.strip().lower()
            enabled_channels = [
                channel for channel in enabled_channels if channel.name == channel_name
                or channel.username.lower() == requested_channel
            ]
            if not enabled_channels:
                raise ValueError(f"Enabled channel is not configured: {channel_name}")

        summary = CollectionSummary()
        client = self.telegram_client or build_telegram_client(self.settings)
        should_disconnect = self.telegram_client is None

        if should_disconnect:
            await client.connect()
            if not await client.is_user_authorized():
                raise TelegramSessionNotAuthorizedError(
                    "Telegram session is not authorized. Run `python -m app.cli telegram-login` "
                    "first to create an authorized session."
                )

        try:
            for channel_config in enabled_channels:
                await self.rate_limiter.wait()
                username = channel_config.username
                entity = await run_with_floodwait_retry(
                    lambda username=username: client.get_entity(username)
                )
                telegram_id = int(utils.get_peer_id(entity))

                with self.session_factory() as session:
                    channel_repo = ChannelRepository(session)
                    channel = channel_repo.upsert_from_config(
                        channel_config, telegram_id=telegram_id
                    )
                    last_message_id = channel.last_message_id
                    session.commit()

                logger.info(
                    "Collecting channel",
                    extra={
                        "channel_name": channel_config.name,
                        "last_message_id": last_message_id,
                    },
                )

                async for message in client.iter_messages(
                    entity,
                    min_id=last_message_id,
                    reverse=False,
                    limit=limit,
                ):
                    await self.rate_limiter.wait()
                    await self._handle_message(channel_config.name, message, summary)
        finally:
            if should_disconnect:
                await client.disconnect()

        return summary

    async def _handle_message(
        self,
        channel_name: str,
        message: Any,
        summary: CollectionSummary,
    ) -> None:
        snapshot = snapshot_message(message, self.settings.supported_extensions)

        if not self._should_record_message(snapshot):
            summary.skipped_messages += 1
            return

        try:
            with self.session_factory() as session:
                channel_repo = ChannelRepository(session)
                channel = channel_repo.get_by_name(channel_name)
                if channel is None:
                    raise RuntimeError(f"Channel was not initialized: {channel_name}")

                message_repo = MessageRepository(session)
                file_repo = FileRepository(session)
                message_record = message_repo.create_from_snapshot(channel, snapshot)

                existing_file = file_repo.get_for_message(message_record)
                if existing_file is not None:
                    channel_repo.advance_last_message_id(channel, snapshot.telegram_message_id)
                    session.commit()
                    return

                if snapshot.has_media and snapshot.is_supported_media:
                    downloaded = await download_message_media(
                        message,
                        incoming_root=self.settings.incoming_storage_dir,
                        channel_name=channel_name,
                        message_id=snapshot.telegram_message_id,
                        filename=snapshot.file_name or f"message_{snapshot.telegram_message_id}",
                    )
                    file_hash = sha256_file(downloaded.path)
                    duplicate_check = Deduplicator(file_repo).check(file_hash)
                    status = (
                        FileStatus.DUPLICATE
                        if duplicate_check.is_duplicate
                        else FileStatus.DOWNLOADED
                    )
                    file_repo.create_or_update_for_message(
                        message_record,
                        original_filename=snapshot.file_name or downloaded.path.name,
                        mime_type=snapshot.mime_type,
                        extension=snapshot.extension,
                        size_bytes=downloaded.size_bytes,
                        sha256=file_hash,
                        storage_path=str(downloaded.path),
                        status=status,
                        duplicate_of_file_id=(
                            duplicate_check.existing_file.id
                            if duplicate_check.existing_file is not None
                            else None
                        ),
                    )
                    summary.downloaded_files += 1
                    if duplicate_check.is_duplicate:
                        summary.duplicate_files += 1
                elif snapshot.has_media:
                    file_repo.create_or_update_for_message(
                        message_record,
                        original_filename=snapshot.file_name
                        or f"message_{snapshot.telegram_message_id}",
                        mime_type=snapshot.mime_type,
                        extension=snapshot.extension,
                        size_bytes=snapshot.file_size,
                        sha256=None,
                        storage_path=None,
                        status=FileStatus.UNSUPPORTED,
                        error_message="Unsupported extension",
                    )
                    summary.unsupported_files += 1

                channel_repo.advance_last_message_id(channel, snapshot.telegram_message_id)
                summary.new_messages += 1
                session.commit()
        except Exception as exc:
            summary.failed_messages += 1
            logger.exception(
                "Message collection failed",
                extra={
                    "channel_name": channel_name,
                    "telegram_message_id": snapshot.telegram_message_id,
                    "error": str(exc),
                },
            )

    def _should_record_message(self, snapshot: TelegramMessageSnapshot) -> bool:
        if snapshot.has_media:
            return True
        return self.settings.telegram_collect_text_messages
