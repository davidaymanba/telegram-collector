"""SQLAlchemy ORM models for the collector database."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.database.statuses import FileStatus


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Channel(Base, TimestampMixin):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    last_message_id: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)

    messages: Mapped[list[Message]] = relationship(back_populates="channel")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("channel_id", "telegram_message_id", name="uq_message_channel_msg"),
        Index("ix_messages_channel_msg", "channel_id", "telegram_message_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), nullable=False)
    telegram_message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    message_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    channel: Mapped[Channel] = relationship(back_populates="messages")
    file: Mapped[CollectedFile | None] = relationship(back_populates="message")


class CollectedFile(Base, TimestampMixin):
    __tablename__ = "files"
    __table_args__ = (
        Index("ix_files_sha256", "sha256"),
        Index("ix_files_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"), unique=True, nullable=False)
    duplicate_of_file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id"), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    extension: Mapped[str | None] = mapped_column(String(20), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_text_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(40),
        default=FileStatus.DISCOVERED.value,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    message: Mapped[Message] = relationship(back_populates="file")
    duplicate_of: Mapped[CollectedFile | None] = relationship(remote_side=[id])
    classification: Mapped[Classification | None] = relationship(back_populates="file")
    processing_logs: Mapped[list[ProcessingLog]] = relationship(back_populates="file")


class Classification(Base):
    __tablename__ = "classifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"), unique=True, nullable=False)
    subject_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    classifier_version: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    file: Mapped[CollectedFile] = relationship(back_populates="classification")


class ProcessingRun(Base):
    __tablename__ = "processing_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    new_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    classified_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unclassified_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unsupported_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class ProcessingLog(Base):
    __tablename__ = "processing_logs"
    __table_args__ = (Index("ix_processing_logs_file_stage", "file_id", "stage"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[int | None] = mapped_column(ForeignKey("files.id"), nullable=True)
    stage: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    file: Mapped[CollectedFile | None] = relationship(back_populates="processing_logs")
