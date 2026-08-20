from app.config.loaders import ChannelConfig
from app.database.models import Channel
from app.database.repositories.channels import ChannelRepository
from app.database.repositories.messages import MessageRepository
from app.ingestion.message_handler import TelegramMessageSnapshot


def _snapshot(message_id: int) -> TelegramMessageSnapshot:
    return TelegramMessageSnapshot(
        telegram_message_id=message_id,
        message_date=None,
        caption="caption",
        media_type="document",
        file_name="lecture.pdf",
        file_size=100,
        mime_type="application/pdf",
        extension=".pdf",
        has_media=True,
        is_supported_media=True,
        telegram_metadata={},
    )


def test_channel_last_message_id_only_advances_forward(db_session_factory) -> None:
    with db_session_factory() as session:
        repo = ChannelRepository(session)
        channel = repo.upsert_from_config(
            ChannelConfig(name="database", username="@database_channel"),
            telegram_id=123,
        )
        repo.advance_last_message_id(channel, 10)
        repo.advance_last_message_id(channel, 8)
        session.commit()

    with db_session_factory() as session:
        channel = session.get(Channel, 1)
        assert channel is not None
        assert channel.last_message_id == 10


def test_message_creation_is_idempotent(db_session_factory) -> None:
    with db_session_factory() as session:
        channel = ChannelRepository(session).upsert_from_config(
            ChannelConfig(name="database", username="@database_channel"),
            telegram_id=123,
        )
        repo = MessageRepository(session)

        first = repo.create_from_snapshot(channel, _snapshot(5))
        second = repo.create_from_snapshot(channel, _snapshot(5))
        session.commit()

        assert first.id == second.id

