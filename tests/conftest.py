from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import Settings
from app.database.session import create_database_engine, create_session_factory, init_db


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    channels_path = config_dir / "channels.yaml"
    subjects_path = config_dir / "subjects.yaml"
    channels_path.write_text(
        """
channels:
  - name: database
    username: "@database_channel"
    enabled: true
""",
        encoding="utf-8",
    )
    subjects_path.write_text(
        """
subjects:
  - code: DB101
    name_ar: "قواعد البيانات"
    name_en: "Database"
  - code: NET201
    name_ar: "شبكات"
    name_en: "Computer Networks"
""",
        encoding="utf-8",
    )
    storage_root = tmp_path / "storage"
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        channels_config_path=channels_path,
        subjects_config_path=subjects_path,
        storage_root=storage_root,
        incoming_storage_dir=storage_root / "incoming",
        processed_storage_dir=storage_root / "processed",
        unclassified_storage_dir=storage_root / "unclassified",
        lock_file_path=storage_root / "collector.lock",
        telegram_request_delay_seconds=0.2,
        min_pdf_text_chars=20,
        ai_provider="none",
    )


@pytest.fixture
def db_session_factory(test_settings: Settings) -> Iterator[sessionmaker[Session]]:
    engine = create_database_engine(test_settings)
    init_db(engine)
    yield create_session_factory(engine)
    engine.dispose()

