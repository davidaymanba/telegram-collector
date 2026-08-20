from pathlib import Path

from sqlalchemy import select

from app.config.loaders import load_channels_config, load_subjects_config
from app.database.models import CollectedFile, Message, ProcessingRun
from app.web.admin import (
    build_overview,
    create_manual_file,
    delete_file,
    delete_message,
    delete_run,
    seed_demo_data,
    update_channel_state,
    update_file,
    upsert_channel,
    upsert_message,
    upsert_subject,
)


def test_upsert_channel_updates_yaml(test_settings) -> None:
    upsert_channel(
        test_settings,
        {"name": "database", "username": "@new_database_channel", "enabled": False},
    )

    config = load_channels_config(test_settings.channels_config_path)

    assert len(config.channels) == 1
    assert config.channels[0].username == "@new_database_channel"
    assert config.channels[0].enabled is False


def test_upsert_subject_updates_yaml(test_settings) -> None:
    upsert_subject(
        test_settings,
        {"code": "cs101", "name_ar": "مقدمة برمجة", "name_en": "Programming"},
    )

    config = load_subjects_config(test_settings.subjects_config_path)

    assert "CS101" in config.subject_codes


def test_seed_demo_data_populates_overview(test_settings, db_session_factory) -> None:
    with db_session_factory() as session:
        seed_demo_data(test_settings, session)
        overview = build_overview(test_settings, session)

    assert overview["summary"]["files"] == 6
    assert overview["summary"]["classified"] == 2
    assert overview["summary"]["duplicates"] == 1
    assert overview["summary"]["failed"] == 1
    assert len(overview["recent_files"]) == 6


def test_update_channel_state_creates_database_channel(test_settings, db_session_factory) -> None:
    with db_session_factory() as session:
        channel = update_channel_state(
            test_settings,
            session,
            {"name": "database", "last_message_id": 123, "status": "paused"},
        )

    assert channel["last_message_id"] == 123
    assert channel["status"] == "paused"
    assert channel["last_run_at"] is not None


def test_message_and_file_crud(test_settings, db_session_factory) -> None:
    with db_session_factory() as session:
        message = upsert_message(
            test_settings,
            session,
            {
                "channel": "database",
                "telegram_message_id": 5001,
                "caption": "manual lecture",
                "media_type": "document",
            },
        )
        updated_message = upsert_message(
            test_settings,
            session,
            {
                "id": message["id"],
                "channel": "database",
                "telegram_message_id": 5002,
                "caption": "updated lecture",
                "media_type": "document",
            },
        )
        file_record = create_manual_file(
            test_settings,
            session,
            {
                "message_id": updated_message["id"],
                "filename": "manual-lecture.pdf",
                "status": "classified",
                "subject_code": "DB101",
                "content_type": "lecture",
                "confidence": 0.88,
                "evidence": "manual\nlecture",
                "content": "demo pdf bytes",
            },
        )
        storage_path = Path(file_record["storage_path"])
        edited_file = update_file(
            test_settings,
            session,
            file_record["id"],
            {
                "message_id": updated_message["id"],
                "filename": "renamed.pdf",
                "status": "unclassified",
                "subject_code": "",
                "content_type": "",
                "evidence": "needs review",
            },
        )

        assert updated_message["telegram_message_id"] == 5002
        assert file_record["subject_code"] == "DB101"
        assert storage_path.exists()
        assert edited_file["filename"] == "renamed.pdf"
        assert edited_file["status"] == "unclassified"
        assert edited_file["subject_code"] is None

        delete_file(test_settings, session, file_record["id"])
        assert not storage_path.exists()
        assert session.scalar(
            select(CollectedFile).where(CollectedFile.id == file_record["id"])
        ) is None

        delete_message(test_settings, session, updated_message["id"])
        assert session.scalar(select(Message).where(Message.id == updated_message["id"])) is None


def test_delete_run(test_settings, db_session_factory) -> None:
    with db_session_factory() as session:
        run = ProcessingRun(metadata_json={"command": "manual"})
        session.add(run)
        session.commit()

        result = delete_run(session, run.id)

        assert result == {"deleted": True, "id": run.id}
        assert session.get(ProcessingRun, run.id) is None
