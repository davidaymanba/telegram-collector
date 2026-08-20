"""PDF text extraction using PyMuPDF."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf

from app.processing.text_cleaner import clean_text


@dataclass(frozen=True)
class PdfExtractionResult:
    text: str
    page_count: int
    requires_ocr: bool


class PdfTextExtractor:
    def __init__(self, min_text_chars: int) -> None:
        self.min_text_chars = min_text_chars

    def extract(self, path: Path) -> PdfExtractionResult:
        """Extract embedded text and indicate whether OCR is likely needed."""

        with pymupdf.open(path) as document:
            page_text = [page.get_text("text") for page in document]
            text = clean_text("\n\n".join(page_text))
            return PdfExtractionResult(
                text=text,
                page_count=document.page_count,
                requires_ocr=len(text) < self.min_text_chars,
            )
