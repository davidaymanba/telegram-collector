"""Shared status values for persistence and reports."""

from enum import StrEnum


class FileStatus(StrEnum):
    DISCOVERED = "discovered"
    DOWNLOADED = "downloaded"
    DUPLICATE = "duplicate"
    PROCESSING = "processing"
    TEXT_EXTRACTED = "text_extracted"
    OCR_COMPLETED = "ocr_completed"
    CLASSIFIED = "classified"
    UNCLASSIFIED = "unclassified"
    STORED = "stored"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


class ProcessingLogStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
