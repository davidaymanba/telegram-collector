"""End-to-end file processing pipeline."""

from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.config.loaders import load_subjects_config
from app.config.settings import Settings
from app.database.models import CollectedFile
from app.database.repositories.files import FileRepository
from app.database.repositories.processing import ProcessingRepository
from app.database.statuses import FileStatus, ProcessingLogStatus
from app.processing.classifier import (
    BaseClassifier,
    ClassificationInput,
    ClassificationStatus,
    build_classifier,
    default_allowed_content_types,
)
from app.processing.ocr import TesseractOcrEngine
from app.processing.office_extractor import extract_docx_text, extract_pptx_text
from app.processing.pdf_extractor import PdfTextExtractor
from app.processing.text_cleaner import clean_text
from app.storage.file_storage import FileStorage

logger = logging.getLogger(__name__)


@dataclass
class ProcessingSummary:
    processed: int = 0
    classified: int = 0
    unclassified: int = 0
    unsupported: int = 0
    failed: int = 0


class UnsupportedFileTypeError(Exception):
    pass


class ProcessingPipeline:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker[Session],
        classifier: BaseClassifier | None = None,
        ocr_engine: TesseractOcrEngine | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.classifier = classifier or build_classifier(settings)
        self.ocr_engine = ocr_engine or TesseractOcrEngine(language=settings.ocr_language)
        self.pdf_extractor = PdfTextExtractor(settings.min_pdf_text_chars)
        self.storage = FileStorage(settings)

    async def process_pending(self, *, limit: int | None = None) -> ProcessingSummary:
        summary = ProcessingSummary()
        with self.session_factory() as session:
            pending_files = list(FileRepository(session).pending_for_processing(limit=limit))

        for file_record in pending_files:
            try:
                final_status = await self.process_file(file_record.id)
                summary.processed += 1
                if final_status == FileStatus.CLASSIFIED:
                    summary.classified += 1
                elif final_status == FileStatus.UNCLASSIFIED:
                    summary.unclassified += 1
                elif final_status == FileStatus.UNSUPPORTED:
                    summary.unsupported += 1
            except Exception:
                summary.failed += 1
                logger.exception("Processing failed", extra={"file_id": file_record.id})

        with self.session_factory() as session:
            for file_record in FileRepository(session).pending_for_processing(limit=None):
                logger.debug("File remains pending", extra={"file_id": file_record.id})

        return summary

    async def process_file(self, file_id: int) -> FileStatus | None:
        with self.session_factory() as session:
            file_repo = FileRepository(session)
            processing_repo = ProcessingRepository(session)
            file_record = file_repo.get_by_id(file_id)
            if file_record is None:
                raise FileNotFoundError(f"File record does not exist: {file_id}")
            if file_record.status == FileStatus.DUPLICATE.value:
                return FileStatus.DUPLICATE
            if file_record.status == FileStatus.UNSUPPORTED.value:
                return FileStatus.UNSUPPORTED

            file_repo.update_status(file_record, FileStatus.PROCESSING)
            processing_repo.log(
                file_record=file_record,
                stage="processing_started",
                status=ProcessingLogStatus.SUCCESS,
            )
            session.commit()

        try:
            extracted_text = self._extract_text(file_record)
            decision = await self._classify(file_record, extracted_text)

            with self.session_factory() as session:
                file_repo = FileRepository(session)
                processing_repo = ProcessingRepository(session)
                current_file = file_repo.get_by_id(file_id)
                if current_file is None:
                    raise FileNotFoundError(f"File record does not exist: {file_id}")

                stored = self.storage.store(current_file, decision, extracted_text)
                current_file.storage_path = str(stored.file_path)
                current_file.extracted_text_path = (
                    str(stored.text_path) if stored.text_path else None
                )
                current_file.status = (
                    FileStatus.CLASSIFIED.value
                    if decision.status == ClassificationStatus.CLASSIFIED
                    else FileStatus.UNCLASSIFIED.value
                )
                processing_repo.upsert_classification(current_file, decision)
                processing_repo.log(
                    file_record=current_file,
                    stage="stored",
                    status=ProcessingLogStatus.SUCCESS,
                )
                session.commit()
                return (
                    FileStatus.CLASSIFIED
                    if decision.status == ClassificationStatus.CLASSIFIED
                    else FileStatus.UNCLASSIFIED
                )
        except UnsupportedFileTypeError as exc:
            self._mark_failed_or_unsupported(file_id, FileStatus.UNSUPPORTED, str(exc))
            return FileStatus.UNSUPPORTED
        except Exception as exc:
            self._mark_failed_or_unsupported(file_id, FileStatus.FAILED, str(exc))
            raise

    def _extract_text(self, file_record: CollectedFile) -> str:
        path = Path(file_record.storage_path or "")
        if not path.exists():
            raise FileNotFoundError(f"Incoming file is missing: {path}")

        extension = (file_record.extension or path.suffix).lower()
        mime_type = file_record.mime_type or mimetypes.guess_type(path.name)[0]

        if extension == ".pdf" or mime_type == "application/pdf":
            result = self.pdf_extractor.extract(path)
            if result.requires_ocr and self.settings.ocr_enabled:
                ocr_result = self.ocr_engine.extract_pdf_text(path)
                return ocr_result.text
            return result.text

        if extension in {".jpg", ".jpeg", ".png"}:
            if not self.settings.ocr_enabled:
                raise UnsupportedFileTypeError("OCR is disabled for image file")
            return self.ocr_engine.extract_image_text(path).text

        if extension == ".docx":
            return extract_docx_text(path)

        if extension == ".pptx":
            return extract_pptx_text(path)

        if extension in {".doc", ".ppt"}:
            raise UnsupportedFileTypeError("Legacy Office binary format is not processable")

        raise UnsupportedFileTypeError(f"Unsupported file extension: {extension}")

    async def _classify(self, file_record: CollectedFile, extracted_text: str):
        subjects = load_subjects_config(self.settings.subjects_config_path)
        message = file_record.message
        channel = message.channel
        cleaned = clean_text(extracted_text)
        if not cleaned and not message.caption:
            from app.processing.classifier import ClassificationDecision

            return ClassificationDecision(
                status=ClassificationStatus.UNCLASSIFIED,
                reason="Insufficient text and caption",
                classifier_version=self.classifier.classifier_version,
            )

        request = ClassificationInput(
            filename=file_record.original_filename,
            caption=message.caption,
            channel_name=channel.name,
            extracted_text=cleaned,
            allowed_subjects=subjects.subjects,
            allowed_content_types=default_allowed_content_types(),
        )
        return await self.classifier.classify(request)

    def _mark_failed_or_unsupported(
        self,
        file_id: int,
        status: FileStatus,
        error_message: str,
    ) -> None:
        with self.session_factory() as session:
            file_repo = FileRepository(session)
            processing_repo = ProcessingRepository(session)
            file_record = file_repo.get_by_id(file_id)
            if file_record is None:
                return
            file_repo.update_status(file_record, status, error_message=error_message)
            processing_repo.log(
                file_record=file_record,
                stage="processing",
                status=ProcessingLogStatus.FAILED,
                error_message=error_message,
            )
            session.commit()
