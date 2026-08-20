from app.config.loaders import load_subjects_config
from app.database.models import Channel, Classification, CollectedFile, Message
from app.database.statuses import FileStatus
from app.reports.reporter import Reporter


def _add_file(
    session,
    channel,
    message_id: int,
    status: FileStatus,
    subject: str | None = None,
) -> None:
    message = Message(
        channel_id=channel.id,
        telegram_message_id=message_id,
        caption="caption",
        media_type="document",
        file_name="file.pdf",
        file_size=1,
        telegram_metadata={},
    )
    session.add(message)
    session.flush()
    file_record = CollectedFile(
        message_id=message.id,
        original_filename="file.pdf",
        status=status.value,
        sha256=str(len(channel.messages)),
    )
    session.add(file_record)
    session.flush()
    if subject:
        session.add(
            Classification(
                file_id=file_record.id,
                subject_code=subject,
                content_type="lecture",
                confidence=0.9,
                evidence=["evidence"],
                status="classified",
                classifier_version="test",
            )
        )


def test_report_counts_statuses_and_empty_subjects(test_settings, db_session_factory) -> None:
    subjects = load_subjects_config(test_settings.subjects_config_path)
    with db_session_factory() as session:
        channel = Channel(name="database", username="@database", telegram_id=123)
        session.add(channel)
        session.flush()
        _add_file(session, channel, 101, FileStatus.CLASSIFIED, subject="DB101")
        _add_file(session, channel, 102, FileStatus.UNCLASSIFIED)
        _add_file(session, channel, 103, FileStatus.DUPLICATE)
        _add_file(session, channel, 104, FileStatus.FAILED)
        _add_file(session, channel, 105, FileStatus.UNSUPPORTED)
        session.commit()

    with db_session_factory() as session:
        report = Reporter(session, subjects).generate()

    assert report.new == 5
    assert report.duplicates == 1
    assert report.classified == 1
    assert report.unclassified == 1
    assert report.failed == 1
    assert report.unsupported == 1
    assert report.by_subject == {"DB101": 1}
    assert "NET201" in report.empty_subjects
