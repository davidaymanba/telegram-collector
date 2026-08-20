import hashlib
from pathlib import Path

from app.ingestion.hashing import sha256_file
from app.ingestion.message_handler import snapshot_message
from app.storage.paths import incoming_file_path, safe_filename


class FakeFile:
    def __init__(self, name: str, mime_type: str, size: int = 10) -> None:
        self.name = name
        self.mime_type = mime_type
        self.size = size


class FakeMessage:
    id = 7
    date = None
    message = "محاضرة قواعد البيانات"
    media = object()
    document = object()
    photo = None

    def __init__(self, file: FakeFile) -> None:
        self.file = file


def test_sha256_file_hashes_content(tmp_path: Path) -> None:
    path = tmp_path / "sample.bin"
    path.write_bytes(b"database lecture")

    assert sha256_file(path) == hashlib.sha256(b"database lecture").hexdigest()


def test_snapshot_message_detects_supported_media() -> None:
    snapshot = snapshot_message(
        FakeMessage(FakeFile("lecture.PDF", "application/pdf")),
        supported_extensions=(".pdf",),
    )

    assert snapshot.telegram_message_id == 7
    assert snapshot.extension == ".pdf"
    assert snapshot.is_supported_media is True


def test_snapshot_message_marks_unsupported_extension() -> None:
    snapshot = snapshot_message(
        FakeMessage(FakeFile("program.exe", "application/octet-stream")),
        supported_extensions=(".pdf",),
    )

    assert snapshot.is_supported_media is False


def test_safe_filename_prevents_path_traversal(tmp_path: Path) -> None:
    path = incoming_file_path(tmp_path, "../database", 9, "../../lecture?.pdf")

    assert path == tmp_path / "database" / "9_lecture_.pdf"
    assert safe_filename("../../../") == "file"

