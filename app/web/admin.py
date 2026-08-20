"""Admin-facing services for the local dashboard API."""

from __future__ import annotations

import hashlib
import mimetypes
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.config.loaders import (
    ChannelConfig,
    ChannelsConfig,
    SubjectConfig,
    SubjectsConfig,
    allowed_content_type_values,
    load_channels_config,
    load_subjects_config,
)
from app.config.settings import Settings
from app.database.models import (
    Channel,
    Classification,
    CollectedFile,
    Message,
    ProcessingLog,
    ProcessingRun,
)
from app.database.statuses import FileStatus, ProcessingLogStatus
from app.reports.reporter import Reporter
from app.storage.paths import ensure_child_path, safe_filename


def _write_yaml_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as file_obj:
        yaml.safe_dump(data, file_obj, allow_unicode=True, sort_keys=False)
    os.replace(temp_path, path)


def upsert_channel(settings: Settings, payload: dict[str, Any]) -> ChannelsConfig:
    channels_config = load_channels_config(settings.channels_config_path)
    incoming = ChannelConfig.model_validate(payload)
    updated = False
    channels = []
    for channel in channels_config.channels:
        if channel.name == incoming.name:
            channels.append(incoming)
            updated = True
        else:
            channels.append(channel)
    if not updated:
        channels.append(incoming)

    validated = ChannelsConfig(channels=channels)
    _write_yaml_atomic(
        settings.channels_config_path,
        {"channels": [channel.model_dump() for channel in validated.channels]},
    )
    return validated


def delete_channel(settings: Settings, name: str) -> ChannelsConfig:
    channels_config = load_channels_config(settings.channels_config_path)
    channels = [channel for channel in channels_config.channels if channel.name != name]
    validated = ChannelsConfig(channels=channels)
    _write_yaml_atomic(
        settings.channels_config_path,
        {"channels": [channel.model_dump() for channel in validated.channels]},
    )
    return validated


def upsert_subject(settings: Settings, payload: dict[str, Any]) -> SubjectsConfig:
    subjects_config = load_subjects_config(settings.subjects_config_path)
    incoming = SubjectConfig.model_validate(payload)
    updated = False
    subjects = []
    for subject in subjects_config.subjects:
        if subject.code == incoming.code:
            subjects.append(incoming)
            updated = True
        else:
            subjects.append(subject)
    if not updated:
        subjects.append(incoming)

    validated = SubjectsConfig(subjects=subjects)
    _write_yaml_atomic(
        settings.subjects_config_path,
        {"subjects": [subject.model_dump() for subject in validated.subjects]},
    )
    return validated


def delete_subject(settings: Settings, code: str) -> SubjectsConfig:
    subjects_config = load_subjects_config(settings.subjects_config_path)
    subjects = [subject for subject in subjects_config.subjects if subject.code != code.upper()]
    validated = SubjectsConfig(subjects=subjects)
    _write_yaml_atomic(
        settings.subjects_config_path,
        {"subjects": [subject.model_dump() for subject in validated.subjects]},
    )
    return validated


def update_channel_state(
    settings: Settings,
    session: Session,
    payload: dict[str, Any],
) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("Channel name is required")

    channel = session.scalar(select(Channel).where(Channel.name == name))
    if channel is None:
        configured = {
            configured_channel.name: configured_channel
            for configured_channel in load_channels_config(settings.channels_config_path).channels
        }.get(name)
        if configured is None:
            raise ValueError(f"Channel is not configured: {name}")
        channel = Channel(
            name=configured.name,
            username=configured.username,
            enabled=configured.enabled,
            last_message_id=0,
            status="active",
        )
        session.add(channel)
        session.flush()

    if "last_message_id" in payload:
        channel.last_message_id = max(0, int(payload["last_message_id"] or 0))
    if "status" in payload:
        channel.status = str(payload["status"] or "active").strip() or "active"
    channel.last_run_at = datetime.now(tz=UTC)
    session.commit()
    return list_channels_from_database(session).get(name, {})


def _file_to_dict(file_record: CollectedFile) -> dict[str, Any]:
    message = file_record.message
    channel = message.channel
    classification = file_record.classification
    return {
        "id": file_record.id,
        "message_id": message.id,
        "filename": file_record.original_filename,
        "status": file_record.status,
        "mime_type": file_record.mime_type,
        "extension": file_record.extension,
        "size_bytes": file_record.size_bytes,
        "sha256": file_record.sha256,
        "storage_path": file_record.storage_path,
        "error_message": file_record.error_message,
        "channel_name": channel.name,
        "telegram_message_id": message.telegram_message_id,
        "caption": message.caption,
        "subject_code": classification.subject_code if classification else None,
        "content_type": classification.content_type if classification else None,
        "confidence": classification.confidence if classification else None,
        "evidence": classification.evidence if classification else [],
        "classification_reason": classification.reason if classification else None,
        "classifier_version": classification.classifier_version if classification else None,
        "created_at": file_record.created_at.isoformat() if file_record.created_at else None,
    }


def list_files(session: Session, *, limit: int = 100) -> list[dict[str, Any]]:
    statement = (
        select(CollectedFile)
        .options(
            joinedload(CollectedFile.message).joinedload(Message.channel),
            joinedload(CollectedFile.classification),
        )
        .order_by(CollectedFile.id.desc())
        .limit(limit)
    )
    return [_file_to_dict(file_record) for file_record in session.scalars(statement).all()]


def get_file(session: Session, file_id: int) -> dict[str, Any]:
    file_record = session.scalar(
        select(CollectedFile)
        .options(
            joinedload(CollectedFile.message).joinedload(Message.channel),
            joinedload(CollectedFile.classification),
        )
        .where(CollectedFile.id == file_id)
    )
    if file_record is None:
        raise ValueError(f"File not found: {file_id}")
    return _file_to_dict(file_record)


def create_manual_file(
    settings: Settings,
    session: Session,
    payload: dict[str, Any],
) -> dict[str, Any]:
    message_id = int(payload.get("message_id") or 0)
    if message_id <= 0:
        raise ValueError("message_id is required")

    message = session.get(Message, message_id)
    if message is None:
        raise ValueError(f"Message not found: {message_id}")
    if message.file is not None:
        raise ValueError("Message already has a file")

    filename = str(payload.get("filename") or "").strip()
    if not filename:
        raise ValueError("Filename is required")

    status = FileStatus(str(payload.get("status") or FileStatus.DISCOVERED.value))
    content = str(payload.get("content") or f"Manual file placeholder for {filename}").encode()
    sha256 = hashlib.sha256(content).hexdigest()
    target_dir = settings.incoming_storage_dir / "manual"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{sha256[:16]}_{safe_filename(filename)}"
    target_path.write_bytes(content)

    file_record = CollectedFile(
        message_id=message.id,
        original_filename=filename,
        mime_type=mimetypes.guess_type(filename)[0] or "application/octet-stream",
        extension=Path(filename).suffix,
        size_bytes=len(content),
        sha256=sha256,
        storage_path=str(target_path),
        status=status.value,
        error_message=str(payload.get("error_message") or "").strip() or None,
    )
    session.add(file_record)
    message.file_name = filename
    message.file_size = len(content)
    if not message.media_type:
        message.media_type = "document"
    session.flush()

    classification_keys = {
        "subject_code",
        "content_type",
        "confidence",
        "evidence",
        "classification_reason",
        "classifier_version",
    }
    if status == FileStatus.CLASSIFIED or classification_keys.intersection(payload):
        _update_classification(settings, file_record, payload)

    session.commit()
    return get_file(session, file_record.id)


def update_file(
    settings: Settings,
    session: Session,
    file_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    file_record = session.scalar(
        select(CollectedFile)
        .options(
            joinedload(CollectedFile.message).joinedload(Message.channel),
            joinedload(CollectedFile.classification),
        )
        .where(CollectedFile.id == file_id)
    )
    if file_record is None:
        raise ValueError(f"File not found: {file_id}")

    if "message_id" in payload:
        message_id = int(payload.get("message_id") or 0)
        if message_id <= 0:
            raise ValueError("message_id must be a positive integer")
        if message_id != file_record.message_id:
            target_message = session.get(Message, message_id)
            if target_message is None:
                raise ValueError(f"Message not found: {message_id}")
            if target_message.file is not None:
                raise ValueError("Target message already has a file")
            file_record.message_id = message_id

    if "filename" in payload:
        filename = str(payload["filename"] or "").strip()
        if not filename:
            raise ValueError("Filename cannot be empty")
        file_record.original_filename = filename

    if "status" in payload:
        status = FileStatus(str(payload["status"]))
        file_record.status = status.value

    if "error_message" in payload:
        file_record.error_message = str(payload.get("error_message") or "").strip() or None

    classification_keys = {
        "subject_code",
        "content_type",
        "confidence",
        "evidence",
        "classification_reason",
        "classifier_version",
    }
    if classification_keys.intersection(payload):
        _update_classification(settings, file_record, payload)

    session.commit()
    return get_file(session, file_id)


def _update_classification(
    settings: Settings,
    file_record: CollectedFile,
    payload: dict[str, Any],
) -> None:
    subjects = load_subjects_config(settings.subjects_config_path)
    allowed_subject_codes = subjects.subject_codes
    allowed_types = allowed_content_type_values()
    existing = file_record.classification

    subject_code = str(
        payload.get("subject_code")
        if "subject_code" in payload
        else existing.subject_code if existing else ""
    ).strip().upper()
    content_type = str(
        payload.get("content_type")
        if "content_type" in payload
        else existing.content_type if existing else ""
    ).strip()

    if subject_code and subject_code not in allowed_subject_codes:
        raise ValueError("Subject code is not configured")
    if content_type and content_type not in allowed_types:
        raise ValueError("Content type is not allowed")
    if file_record.status == FileStatus.CLASSIFIED.value and (not subject_code or not content_type):
        raise ValueError("Classified files require subject_code and content_type")

    if existing is None:
        existing = Classification(
            file_id=file_record.id,
            status=(
                "classified"
                if file_record.status == FileStatus.CLASSIFIED.value
                else "unclassified"
            ),
            classifier_version="manual",
        )
        file_record.classification = existing

    existing.subject_code = subject_code or None
    existing.content_type = content_type or None
    existing.confidence = (
        float(payload["confidence"])
        if payload.get("confidence") not in {None, ""}
        else existing.confidence
    )
    evidence = payload.get("evidence")
    if isinstance(evidence, str):
        existing.evidence = [line.strip() for line in evidence.splitlines() if line.strip()]
    elif isinstance(evidence, list):
        existing.evidence = [str(item).strip() for item in evidence if str(item).strip()]
    existing.reason = str(payload.get("classification_reason") or "").strip() or None
    existing.classifier_version = (
        str(payload.get("classifier_version") or "manual").strip() or "manual"
    )
    classified = (
        existing.subject_code is not None
        and existing.content_type is not None
        and file_record.status == FileStatus.CLASSIFIED.value
    )
    existing.status = (
        "classified"
        if classified
        else "unclassified"
    )


def delete_file(settings: Settings, session: Session, file_id: int) -> dict[str, Any]:
    file_record = session.get(CollectedFile, file_id)
    if file_record is None:
        raise ValueError(f"File not found: {file_id}")

    for raw_path in [file_record.storage_path, file_record.extracted_text_path]:
        path = Path(raw_path) if raw_path else None
        if path and path.exists():
            try:
                safe_path = ensure_child_path(settings.storage_root, path)
                safe_path.unlink()
            except ValueError:
                pass

    session.query(CollectedFile).filter(CollectedFile.duplicate_of_file_id == file_id).update(
        {CollectedFile.duplicate_of_file_id: None},
        synchronize_session=False,
    )
    session.query(ProcessingLog).filter(ProcessingLog.file_id == file_id).delete()
    session.query(Classification).filter(Classification.file_id == file_id).delete()
    session.delete(file_record)
    session.commit()
    return {"deleted": True, "id": file_id}


def _message_to_dict(message: Message) -> dict[str, Any]:
    return {
        "id": message.id,
        "channel": message.channel.name,
        "telegram_message_id": message.telegram_message_id,
        "message_date": message.message_date.isoformat() if message.message_date else None,
        "caption": message.caption,
        "media_type": message.media_type,
        "file_name": message.file_name,
        "file_size": message.file_size,
        "has_file": message.file is not None,
        "file_id": message.file.id if message.file else None,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


def _ensure_database_channel(settings: Settings, session: Session, name: str) -> Channel:
    channel = session.scalar(select(Channel).where(Channel.name == name))
    if channel is not None:
        return channel

    configured = {
        configured_channel.name: configured_channel
        for configured_channel in load_channels_config(settings.channels_config_path).channels
    }.get(name)
    if configured is None:
        raise ValueError(f"Channel is not configured: {name}")

    channel = Channel(
        name=configured.name,
        username=configured.username,
        enabled=configured.enabled,
        last_message_id=0,
        status="active",
    )
    session.add(channel)
    session.flush()
    return channel


def get_message(session: Session, message_id: int) -> dict[str, Any]:
    message = session.scalar(
        select(Message)
        .options(joinedload(Message.channel), joinedload(Message.file))
        .where(Message.id == message_id)
    )
    if message is None:
        raise ValueError(f"Message not found: {message_id}")
    return _message_to_dict(message)


def upsert_message(
    settings: Settings,
    session: Session,
    payload: dict[str, Any],
) -> dict[str, Any]:
    channel_name = str(payload.get("channel") or payload.get("channel_name") or "").strip()
    if not channel_name:
        raise ValueError("Channel is required")
    channel = _ensure_database_channel(settings, session, channel_name)

    telegram_message_id = int(payload.get("telegram_message_id") or 0)
    if telegram_message_id <= 0:
        raise ValueError("telegram_message_id is required")

    message_id = int(payload.get("id") or 0)
    if message_id:
        message = session.get(Message, message_id)
        if message is None:
            raise ValueError(f"Message not found: {message_id}")
    else:
        message = session.scalar(
            select(Message).where(
                Message.channel_id == channel.id,
                Message.telegram_message_id == telegram_message_id,
            )
        )
        if message is None:
            message = Message(
                channel_id=channel.id,
                telegram_message_id=telegram_message_id,
                message_date=datetime.now(tz=UTC),
                telegram_metadata={"manual": True},
            )
            session.add(message)
            session.flush()

    duplicate = session.scalar(
        select(Message).where(
            Message.channel_id == channel.id,
            Message.telegram_message_id == telegram_message_id,
            Message.id != message.id,
        )
    )
    if duplicate is not None:
        raise ValueError("Another message already uses this Telegram ID in the same channel")

    message.channel_id = channel.id
    message.telegram_message_id = telegram_message_id
    message.caption = str(payload.get("caption") or "").strip() or None
    message.media_type = str(payload.get("media_type") or "").strip() or None
    message.file_name = str(payload.get("file_name") or "").strip() or None
    file_size = payload.get("file_size")
    message.file_size = int(file_size) if file_size not in {None, ""} else None

    channel.last_message_id = max(channel.last_message_id, telegram_message_id)
    channel.last_run_at = datetime.now(tz=UTC)
    session.commit()
    return get_message(session, message.id)


def list_messages(session: Session, *, limit: int = 100) -> list[dict[str, Any]]:
    statement = (
        select(Message)
        .options(joinedload(Message.channel), joinedload(Message.file))
        .order_by(Message.id.desc())
        .limit(limit)
    )
    return [_message_to_dict(message) for message in session.scalars(statement).unique().all()]


def delete_message(settings: Settings, session: Session, message_id: int) -> dict[str, Any]:
    message = session.scalar(
        select(Message).options(joinedload(Message.file)).where(Message.id == message_id)
    )
    if message is None:
        raise ValueError(f"Message not found: {message_id}")
    if message.file is not None:
        delete_file(settings, session, message.file.id)
        message = session.get(Message, message_id)
        if message is None:
            return {"deleted": True, "id": message_id}
    session.delete(message)
    session.commit()
    return {"deleted": True, "id": message_id}


def list_runs(session: Session, *, limit: int = 30) -> list[dict[str, Any]]:
    runs = session.scalars(
        select(ProcessingRun).order_by(ProcessingRun.id.desc()).limit(limit)
    ).all()
    return [
        {
            "id": run.id,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "new_count": run.new_count,
            "duplicate_count": run.duplicate_count,
            "classified_count": run.classified_count,
            "unclassified_count": run.unclassified_count,
            "failed_count": run.failed_count,
            "unsupported_count": run.unsupported_count,
            "metadata": run.metadata_json,
        }
        for run in runs
    ]


def delete_run(session: Session, run_id: int) -> dict[str, Any]:
    run = session.get(ProcessingRun, run_id)
    if run is None:
        raise ValueError(f"Run not found: {run_id}")
    session.delete(run)
    session.commit()
    return {"deleted": True, "id": run_id}


def list_channels_from_database(session: Session) -> dict[str, dict[str, Any]]:
    channels = session.scalars(select(Channel)).all()
    return {
        channel.name: {
            "telegram_id": channel.telegram_id,
            "username": channel.username,
            "enabled": channel.enabled,
            "last_message_id": channel.last_message_id,
            "last_run_at": channel.last_run_at.isoformat() if channel.last_run_at else None,
            "status": channel.status,
        }
        for channel in channels
    }


def build_overview(settings: Settings, session: Session) -> dict[str, Any]:
    channels_config = load_channels_config(settings.channels_config_path)
    subjects_config = load_subjects_config(settings.subjects_config_path)
    report = Reporter(session, subjects_config).generate()
    db_channels = list_channels_from_database(session)
    status_counts = dict(
        session.execute(
            select(CollectedFile.status, func.count(CollectedFile.id)).group_by(
                CollectedFile.status
            )
        ).all()
    )
    if settings.database_url.startswith("mysql"):
        database_label = "MySQL"
    elif settings.database_url.startswith("postgresql"):
        database_label = "PostgreSQL"
    else:
        database_label = "SQLite"

    channels = []
    for channel in channels_config.channels:
        database = db_channels.get(channel.name, {})
        channels.append(
            {
                **channel.model_dump(),
                "database": database,
                "source": "config",
            }
        )
    configured_channel_names = {channel.name for channel in channels_config.channels}
    for name, database in sorted(db_channels.items()):
        if name in configured_channel_names:
            continue
        channels.append(
            {
                "name": name,
                "username": database.get("username") or f"@{name}",
                "enabled": bool(database.get("enabled", True)),
                "database": database,
                "source": "database",
            }
        )

    return {
        "health": {
            "healthy": True,
            "database": database_label,
            "ai_provider": settings.ai_provider,
            "ocr_language": settings.ocr_language,
            "collect_text_messages": settings.telegram_collect_text_messages,
        },
        "summary": {
            "enabled_channels": len(channels_config.enabled_channels),
            "total_channels": len(channels_config.channels),
            "subjects": len(subjects_config.subjects),
            "files": sum(status_counts.values()),
            "classified": report.classified,
            "unclassified": report.unclassified,
            "duplicates": report.duplicates,
            "failed": report.failed,
            "unsupported": report.unsupported,
        },
        "report": {
            "new": report.new,
            "duplicates": report.duplicates,
            "classified": report.classified,
            "unclassified": report.unclassified,
            "failed": report.failed,
            "unsupported": report.unsupported,
            "by_subject": report.by_subject,
            "by_content_type": report.by_content_type,
            "empty_subjects": report.empty_subjects,
        },
        "channels": channels,
        "subjects": [subject.model_dump() for subject in subjects_config.subjects],
        "recent_files": list_files(session, limit=20),
        "recent_runs": list_runs(session, limit=10),
        "recent_messages": list_messages(session, limit=20),
        "options": {
            "file_statuses": [status.value for status in FileStatus],
            "content_types": sorted(allowed_content_type_values()),
            "subject_codes": sorted(subjects_config.subject_codes),
        },
    }


def _demo_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _ensure_demo_channel(session: Session, name: str, username: str, telegram_id: int) -> Channel:
    channel = session.scalar(select(Channel).where(Channel.name == name))
    if channel is None:
        channel = Channel(
            name=name,
            username=username,
            telegram_id=telegram_id,
            enabled=True,
            last_message_id=0,
        )
        session.add(channel)
        session.flush()
    else:
        channel.username = username
        channel.telegram_id = telegram_id
        channel.enabled = True
    return channel


def _ensure_demo_file(
    *,
    settings: Settings,
    session: Session,
    channel: Channel,
    message_id: int,
    filename: str,
    content: bytes,
    status: FileStatus,
    subject_code: str | None = None,
    content_type: str | None = None,
    duplicate_of: CollectedFile | None = None,
    error_message: str | None = None,
) -> CollectedFile:
    message = session.scalar(
        select(Message).where(
            Message.channel_id == channel.id,
            Message.telegram_message_id == message_id,
        )
    )
    if message is None:
        message = Message(
            channel_id=channel.id,
            telegram_message_id=message_id,
            message_date=datetime.now(tz=UTC) - timedelta(minutes=message_id % 30),
            caption=f"Demo content for {filename}",
            media_type="document",
            file_name=filename,
            file_size=len(content),
            telegram_metadata={"demo": True},
        )
        session.add(message)
        session.flush()

    sha256 = _demo_hash(content)
    target_root = (
        settings.processed_storage_dir
        if status == FileStatus.CLASSIFIED and subject_code and content_type
        else settings.unclassified_storage_dir
    )
    target_dir = target_root
    if status == FileStatus.CLASSIFIED and subject_code and content_type:
        target_dir = target_root / safe_filename(subject_code) / safe_filename(content_type)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{sha256[:16]}_{safe_filename(filename)}"
    if not target_path.exists():
        target_path.write_bytes(content)

    file_record = session.scalar(
        select(CollectedFile).where(CollectedFile.message_id == message.id)
    )
    if file_record is None:
        file_record = CollectedFile(message_id=message.id, original_filename=filename)
        session.add(file_record)

    file_record.original_filename = filename
    file_record.mime_type = "application/pdf" if filename.endswith(".pdf") else "image/png"
    file_record.extension = Path(filename).suffix
    file_record.size_bytes = len(content)
    file_record.sha256 = sha256
    file_record.storage_path = str(target_path)
    file_record.status = status.value
    file_record.duplicate_of_file_id = duplicate_of.id if duplicate_of else None
    file_record.error_message = error_message
    session.flush()

    if subject_code and content_type:
        classification = file_record.classification
        if classification is None:
            classification = Classification(
                file_id=file_record.id,
                status="classified",
                classifier_version="demo",
            )
            session.add(classification)
        classification.subject_code = subject_code
        classification.content_type = content_type
        classification.confidence = 0.93
        classification.evidence = ["demo seed", subject_code]
        classification.status = "classified"
        classification.reason = None
        classification.classifier_version = "demo"

    session.add(
        ProcessingLog(
            file_id=file_record.id,
            stage="demo_seed",
            status=ProcessingLogStatus.SUCCESS.value,
        )
    )
    return file_record


def seed_demo_data(settings: Settings, session: Session) -> dict[str, Any]:
    """Insert idempotent demo records so the frontend can be exercised immediately."""

    db_channel = _ensure_demo_channel(session, "database", "@database_channel", 100001)
    net_channel = _ensure_demo_channel(session, "networks", "@networks_channel", 100002)

    file_one = _ensure_demo_file(
        settings=settings,
        session=session,
        channel=db_channel,
        message_id=9001,
        filename="db-normalization-lecture.pdf",
        content=b"Demo PDF placeholder: database normalization lecture",
        status=FileStatus.CLASSIFIED,
        subject_code="DB101",
        content_type="lecture",
    )
    _ensure_demo_file(
        settings=settings,
        session=session,
        channel=net_channel,
        message_id=9002,
        filename="networks-previous-exam.pdf",
        content=b"Demo PDF placeholder: routing previous exam",
        status=FileStatus.CLASSIFIED,
        subject_code="NET201",
        content_type="previous_exam",
    )
    _ensure_demo_file(
        settings=settings,
        session=session,
        channel=db_channel,
        message_id=9003,
        filename="unclear-scan.pdf",
        content=b"Demo scanned document with unclear subject",
        status=FileStatus.UNCLASSIFIED,
    )
    _ensure_demo_file(
        settings=settings,
        session=session,
        channel=db_channel,
        message_id=9004,
        filename="db-normalization-copy.pdf",
        content=b"Demo PDF placeholder: database normalization lecture",
        status=FileStatus.DUPLICATE,
        duplicate_of=file_one,
    )
    _ensure_demo_file(
        settings=settings,
        session=session,
        channel=net_channel,
        message_id=9005,
        filename="broken-image.png",
        content=b"not a real image",
        status=FileStatus.FAILED,
        error_message="Demo OCR failure",
    )
    _ensure_demo_file(
        settings=settings,
        session=session,
        channel=net_channel,
        message_id=9006,
        filename="legacy-slides.ppt",
        content=b"legacy ppt",
        status=FileStatus.UNSUPPORTED,
        error_message="Legacy Office binary format is not processable",
    )

    db_channel.last_message_id = max(db_channel.last_message_id, 9004)
    net_channel.last_message_id = max(net_channel.last_message_id, 9006)
    now = datetime.now(tz=UTC)
    db_channel.last_run_at = now
    net_channel.last_run_at = now

    run = ProcessingRun(
        finished_at=now,
        new_count=6,
        duplicate_count=1,
        classified_count=2,
        unclassified_count=1,
        failed_count=1,
        unsupported_count=1,
        metadata_json={"command": "demo_seed"},
    )
    session.add(run)
    session.commit()
    return {"seeded": True, "files": 6}
