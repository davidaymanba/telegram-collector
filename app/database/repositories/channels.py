"""Repository operations for Telegram channels."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.loaders import ChannelConfig
from app.database.models import Channel


class ChannelRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_from_config(
        self,
        channel_config: ChannelConfig,
        telegram_id: int | None = None,
    ) -> Channel:
        channel = self.session.scalar(select(Channel).where(Channel.name == channel_config.name))
        if channel is None:
            channel = Channel(
                name=channel_config.name,
                username=channel_config.username,
                enabled=channel_config.enabled,
                telegram_id=telegram_id,
            )
            self.session.add(channel)
            self.session.flush()
            return channel

        channel.username = channel_config.username
        channel.enabled = channel_config.enabled
        if telegram_id is not None:
            channel.telegram_id = telegram_id
        return channel

    def get_by_name(self, name: str) -> Channel | None:
        return self.session.scalar(select(Channel).where(Channel.name == name))

    def advance_last_message_id(self, channel: Channel, message_id: int) -> None:
        if message_id > channel.last_message_id:
            channel.last_message_id = message_id
        channel.last_run_at = datetime.now(tz=UTC)
