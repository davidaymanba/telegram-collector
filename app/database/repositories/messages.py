"""Repository operations for Telegram messages."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Channel, Message
from app.ingestion.message_handler import TelegramMessageSnapshot


class MessageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_telegram_id(self, channel: Channel, telegram_message_id: int) -> Message | None:
        return self.session.scalar(
            select(Message).where(
                Message.channel_id == channel.id,
                Message.telegram_message_id == telegram_message_id,
            )
        )

    def create_from_snapshot(self, channel: Channel, snapshot: TelegramMessageSnapshot) -> Message:
        existing = self.get_by_telegram_id(channel, snapshot.telegram_message_id)
        if existing is not None:
            return existing

        message = Message(
            channel_id=channel.id,
            telegram_message_id=snapshot.telegram_message_id,
            message_date=snapshot.message_date,
            caption=snapshot.caption,
            media_type=snapshot.media_type,
            file_name=snapshot.file_name,
            file_size=snapshot.file_size,
            telegram_metadata=snapshot.telegram_metadata,
        )
        self.session.add(message)
        self.session.flush()
        return message
