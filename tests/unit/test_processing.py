from __future__ import annotations

from pathlib import Path

import pymupdf

from app.config.settings import Settings
from app.database.models import Channel, CollectedFile, Message
from app.database.statuses import FileStatus
from app.processing.classifier import (
    BaseClassifier,
    ClassificationDecision,
    ClassificationInput,
    ClassificationStatus,
)
from app.processing.pdf_extractor import PdfTextExtractor
from app.processing.pipeline import ProcessingPipeline
from app.storage.file_storage import FileStorage


class FakeClassifier(BaseClassifier):
    classifier_version = "fake"

    async def classify(self, request: ClassificationInput) -> ClassificationDecision:
        return ClassificationDecision(
            status=ClassificationStatus.CLASSIFIED,
            subject_code="DB101",
            content_type="lecture",
            confidence=0.95,
            evidence=["database"],
            classifier_version=self.classifier_version,
        )


class FakeOcrEngine:
    def __init__(self) -> None:
        self.pdf_calls = 0

    def extract_pdf_text(self, path: Path):
        from app.processing.ocr import OcrResult

        self.pdf_calls += 1
        return OcrResult(text="قواعد البيانات database", page_count=1)

    def extract_image_text(self, path: Path):
        from app.processing.ocr import OcrResult

        return OcrResult(text="قواعد البيانات database", page_count=1)


def _create_pdf(path: Path, text: str | None = None) -> None:
    document = pymupdf.open()
    page = document.new_page()
    if text:
        page.insert_text((72, 72), text)
    document.save(path)
    document.close()


def _seed_file(db_session_factory, path: Path, extension: str = ".pdf") -> int:
    with db_session_factory() as session:
        channel = Channel(name="database", username="@database", telegram_id=123)
        session.add(channel)
        session.flush()
        message = Message(
            channel_id=channel.id,
            telegram_message_id=1,
            caption="database lecture",
            media_type="document",
            file_name=path.name,
            file_size=path.stat().st_size,
            telegram_metadata={},
        )
        session.add(message)
        session.flush()
        file_record = CollectedFile(
            message_id=message.id,
            original_filename=path.name,
            mime_type="application/pdf" if extension == ".pdf" else None,
            extension=extension,
            size_bytes=path.stat().st_size,
            sha256="a" * 64,
            storage_path=str(path),
            status=FileStatus.DOWNLOADED.value,
        )
        session.add(file_record)
        session.commit()
        return file_record.id


def test_pdf_text_extractor_reads_normal_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "lecture.pdf"
    _create_pdf(pdf_path, "Database normalization lecture")

    result = PdfTextExtractor(min_text_chars=5).extract(pdf_path)

    assert "Database normalization" in result.text
    assert result.requires_ocr is False


def test_processing_pipeline_classifies_and_stores_pdf(
    test_settings: Settings,
    db_session_factory,
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "lecture.pdf"
    _create_pdf(pdf_path, "Database normalization lecture")
    file_id = _seed_file(db_session_factory, pdf_path)

    pipeline = ProcessingPipeline(
        settings=test_settings,
        session_factory=db_session_factory,
        classifier=FakeClassifier(),
    )

    import asyncio

    final_status = asyncio.run(pipeline.process_file(file_id))

    with db_session_factory() as session:
        stored = session.get(CollectedFile, file_id)
        assert final_status == FileStatus.CLASSIFIED
        assert stored is not None
        assert stored.status == FileStatus.CLASSIFIED.value
        assert "/processed/DB101/lecture/" in stored.storage_path
        assert stored.classification.subject_code == "DB101"


def test_processing_pipeline_uses_ocr_when_pdf_text_is_too_short(
    test_settings: Settings,
    db_session_factory,
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "scan.pdf"
    _create_pdf(pdf_path)
    file_id = _seed_file(db_session_factory, pdf_path)
    fake_ocr = FakeOcrEngine()

    pipeline = ProcessingPipeline(
        settings=test_settings,
        session_factory=db_session_factory,
        classifier=FakeClassifier(),
        ocr_engine=fake_ocr,
    )

    import asyncio

    asyncio.run(pipeline.process_file(file_id))

    assert fake_ocr.pdf_calls == 1


def test_legacy_office_file_is_recorded_unsupported(
    test_settings: Settings,
    db_session_factory,
    tmp_path: Path,
) -> None:
    doc_path = tmp_path / "legacy.doc"
    doc_path.write_bytes(b"legacy")
    file_id = _seed_file(db_session_factory, doc_path, extension=".doc")

    pipeline = ProcessingPipeline(
        settings=test_settings,
        session_factory=db_session_factory,
        classifier=FakeClassifier(),
    )

    import asyncio

    final_status = asyncio.run(pipeline.process_file(file_id))

    with db_session_factory() as session:
        stored = session.get(CollectedFile, file_id)
        assert final_status == FileStatus.UNSUPPORTED
        assert stored is not None
        assert stored.status == FileStatus.UNSUPPORTED.value


def test_file_storage_creates_classified_path(test_settings: Settings, tmp_path: Path) -> None:
    source = tmp_path / "unsafe.pdf"
    source.write_bytes(b"content")
    file_record = CollectedFile(
        id=5,
        original_filename="../../محاضرة?.pdf",
        sha256="b" * 64,
        storage_path=str(source),
    )
    decision = ClassificationDecision(
        status=ClassificationStatus.CLASSIFIED,
        subject_code="DB101",
        content_type="lecture",
        confidence=0.9,
        evidence=["database"],
        classifier_version="test",
    )

    stored = FileStorage(test_settings).store(file_record, decision, "text")

    assert stored.file_path.exists()
    assert stored.file_path.parent.name == "lecture"
    assert stored.file_path.parent.parent.name == "DB101"
    assert stored.text_path is not None
    assert stored.text_path.exists()
