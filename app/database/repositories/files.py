"""Repository operations for collected files."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.database.models import CollectedFile, Message
from app.database.statuses import FileStatus


class FileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_for_message(self, message: Message) -> CollectedFile | None:
        return self.session.scalar(
            select(CollectedFile).where(CollectedFile.message_id == message.id)
        )

    def get_by_id(self, file_id: int) -> CollectedFile | None:
        return self.session.scalar(
            select(CollectedFile)
            .options(
                joinedload(CollectedFile.message).joinedload(Message.channel),
                joinedload(CollectedFile.classification),
            )
            .where(CollectedFile.id == file_id)
        )

    def find_original_by_sha256(self, sha256: str) -> CollectedFile | None:
        return self.session.scalar(
            select(CollectedFile)
            .where(
                CollectedFile.sha256 == sha256,
                CollectedFile.status != FileStatus.DUPLICATE.value,
            )
            .order_by(CollectedFile.id.asc())
        )

    def create_or_update_for_message(
        self,
        message: Message,
        *,
        original_filename: str,
        mime_type: str | None,
        extension: str | None,
        size_bytes: int | None,
        sha256: str | None,
        storage_path: str | None,
        status: FileStatus,
        duplicate_of_file_id: int | None = None,
        error_message: str | None = None,
    ) -> CollectedFile:
        file_record = self.get_for_message(message)
        if file_record is None:
            file_record = CollectedFile(
                message_id=message.id,
                original_filename=original_filename,
            )
            self.session.add(file_record)

        file_record.original_filename = original_filename
        file_record.mime_type = mime_type
        file_record.extension = extension
        file_record.size_bytes = size_bytes
        file_record.sha256 = sha256
        file_record.storage_path = storage_path
        file_record.status = status.value
        file_record.duplicate_of_file_id = duplicate_of_file_id
        file_record.error_message = error_message
        self.session.flush()
        return file_record

    def update_status(
        self,
        file_record: CollectedFile,
        status: FileStatus,
        *,
        error_message: str | None = None,
    ) -> None:
        file_record.status = status.value
        file_record.error_message = error_message

    def pending_for_processing(self, limit: int | None = None) -> Iterable[CollectedFile]:
        statement = (
            select(CollectedFile)
            .where(CollectedFile.status == FileStatus.DOWNLOADED.value)
            .order_by(CollectedFile.id.asc())
        )
        if limit is not None:
            statement = statement.limit(limit)
        return self.session.scalars(statement).all()
