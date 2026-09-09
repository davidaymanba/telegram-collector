from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from app.database.models import Channel, CollectedFile
from app.database.statuses import FileStatus
from app.telegram.collector import TelegramCollector


class FakeTelegramFile:
    def __init__(self, name: str, payload: bytes) -> None:
        self.name = name
        self.mime_type = "application/pdf"
        self.size = len(payload)


class FakeTelegramMessage:
    media = object()
    document = object()
    photo = None

    def __init__(self, message_id: int, payload: bytes) -> None:
        self.id = message_id
        self.date = datetime.now(tz=UTC)
        self.message = f"caption {message_id}"
        self._payload = payload
        self.file = FakeTelegramFile(f"lecture-{message_id}.pdf", payload)

    async def download_media(self, file: str) -> str:
        Path(file).write_bytes(self._payload)
        return file


class FakeTelegramClient:
    def __init__(self, messages: list[FakeTelegramMessage]) -> None:
        self.messages = messages
        self.connected = False
        self.disconnected = False

    async def connect(self) -> None:
        self.connected = True

    async def is_user_authorized(self) -> bool:
        return True

    async def disconnect(self) -> None:
        self.disconnected = True

    async def get_entity(self, username: str) -> object:
        return object()

    def iter_messages(self, entity, *, min_id: int, reverse: bool, limit: int | None):
        async def generator():
            yielded = 0
            for message in self.messages:
                if message.id <= min_id:
                    continue
                if limit is not None and yielded >= limit:
                    break
                yielded += 1
                yield message

        return generator()


def test_collector_downloads_hashes_deduplicates_and_advances_state(
    test_settings,
    db_session_factory,
    monkeypatch,
) -> None:
    test_settings.incoming_storage_dir.mkdir(parents=True)
    monkeypatch.setattr("app.telegram.collector.utils.get_peer_id", lambda entity: 123)
    client = FakeTelegramClient(
        [
            FakeTelegramMessage(1, b"same file"),
            FakeTelegramMessage(2, b"same file"),
        ]
    )
    collector = TelegramCollector(
        settings=test_settings,
        session_factory=db_session_factory,
        telegram_client=client,
    )

    summary = asyncio.run(collector.collect(channel_name="database"))

    assert summary.new_messages == 2
    assert summary.downloaded_files == 2
    assert summary.duplicate_files == 1

    with db_session_factory() as session:
        channel = session.query(Channel).filter_by(name="database").one()
        files = session.query(CollectedFile).order_by(CollectedFile.id).all()
        assert channel.last_message_id == 2
        assert [file.status for file in files] == [
            FileStatus.DOWNLOADED.value,
            FileStatus.DUPLICATE.value,
        ]


def test_collector_accepts_configured_channel_username(
    test_settings,
    db_session_factory,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.telegram.collector.utils.get_peer_id", lambda entity: 123)
    collector = TelegramCollector(
        settings=test_settings,
        session_factory=db_session_factory,
        telegram_client=FakeTelegramClient([]),
    )

    summary = asyncio.run(collector.collect(channel_name="@database_channel"))

    assert summary.new_messages == 0
