"""Duplicate detection based on SHA-256 content hashes."""

from dataclasses import dataclass

from app.database.models import CollectedFile
from app.database.repositories.files import FileRepository


@dataclass(frozen=True)
class DuplicateCheck:
    is_duplicate: bool
    existing_file: CollectedFile | None


class Deduplicator:
    def __init__(self, file_repository: FileRepository) -> None:
        self.file_repository = file_repository

    def check(self, sha256: str) -> DuplicateCheck:
        existing = self.file_repository.find_original_by_sha256(sha256)
        return DuplicateCheck(is_duplicate=existing is not None, existing_file=existing)
