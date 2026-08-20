"""Final storage organization for processed and unclassified files."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.config.settings import Settings
from app.database.models import CollectedFile
from app.processing.classifier import ClassificationDecision, ClassificationStatus
from app.storage.paths import ensure_child_path, safe_filename


@dataclass(frozen=True)
class StoredFile:
    file_path: Path
    text_path: Path | None


class FileStorage:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def store(
        self,
        file_record: CollectedFile,
        decision: ClassificationDecision,
        extracted_text: str,
    ) -> StoredFile:
        source_path = Path(file_record.storage_path or "")
        if not source_path.exists():
            raise FileNotFoundError(f"Stored incoming file is missing: {source_path}")

        if decision.status == ClassificationStatus.CLASSIFIED:
            target_dir = (
                self.settings.processed_storage_dir
                / safe_filename(decision.subject_code or "unknown")
                / safe_filename(decision.content_type or "unknown")
            )
        else:
            target_dir = self.settings.unclassified_storage_dir

        target_dir.mkdir(parents=True, exist_ok=True)
        suffix_name = safe_filename(
            file_record.original_filename, fallback=f"file_{file_record.id}"
        )
        hash_prefix = (file_record.sha256 or f"file_{file_record.id}")[:16]
        final_path = target_dir / f"{hash_prefix}_{file_record.id}_{suffix_name}"
        ensure_child_path(self.settings.storage_root, final_path)

        if source_path.resolve() != final_path.resolve():
            shutil.move(str(source_path), str(final_path))

        text_path = None
        if extracted_text:
            text_dir = self.settings.storage_root / "texts"
            text_dir.mkdir(parents=True, exist_ok=True)
            text_path = text_dir / f"{hash_prefix}_{file_record.id}.txt"
            ensure_child_path(self.settings.storage_root, text_path)
            with text_path.open("w", encoding="utf-8") as file_obj:
                file_obj.write(extracted_text)
            os.chmod(text_path, 0o600)

        return StoredFile(file_path=final_path, text_path=text_path)
