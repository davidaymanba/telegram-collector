"""initial schema"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True, unique=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_message_id", sa.Integer(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "processing_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_count", sa.Integer(), nullable=False),
        sa.Column("classified_count", sa.Integer(), nullable=False),
        sa.Column("unclassified_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("unsupported_count", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("channels.id"), nullable=False),
        sa.Column("telegram_message_id", sa.Integer(), nullable=False),
        sa.Column("message_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("media_type", sa.String(length=80), nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("telegram_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("channel_id", "telegram_message_id", name="uq_message_channel_msg"),
    )
    op.create_index("ix_messages_channel_msg", "messages", ["channel_id", "telegram_message_id"])
    op.create_table(
        "files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "message_id", sa.Integer(), sa.ForeignKey("messages.id"), nullable=False, unique=True
        ),
        sa.Column("duplicate_of_file_id", sa.Integer(), sa.ForeignKey("files.id"), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=True),
        sa.Column("extension", sa.String(length=20), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("extracted_text_path", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_files_sha256", "files", ["sha256"])
    op.create_index("ix_files_status", "files", ["status"])
    op.create_table(
        "classifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("file_id", sa.Integer(), sa.ForeignKey("files.id"), nullable=False, unique=True),
        sa.Column("subject_code", sa.String(length=32), nullable=True),
        sa.Column("content_type", sa.String(length=40), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("classifier_version", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "processing_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("file_id", sa.Integer(), sa.ForeignKey("files.id"), nullable=True),
        sa.Column("stage", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_processing_logs_file_stage", "processing_logs", ["file_id", "stage"])


def downgrade() -> None:
    op.drop_index("ix_processing_logs_file_stage", table_name="processing_logs")
    op.drop_table("processing_logs")
    op.drop_table("classifications")
    op.drop_index("ix_files_status", table_name="files")
    op.drop_index("ix_files_sha256", table_name="files")
    op.drop_table("files")
    op.drop_index("ix_messages_channel_msg", table_name="messages")
    op.drop_table("messages")
    op.drop_table("processing_runs")
    op.drop_table("channels")
