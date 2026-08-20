"""Arabic-capable OCR helpers built around Tesseract."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image

from app.processing.text_cleaner import clean_text


@dataclass(frozen=True)
class OcrResult:
    text: str
    page_count: int


class TesseractOcrEngine:
    def __init__(self, language: str = "ara+eng", zoom: float = 2.0) -> None:
        self.language = language
        self.zoom = zoom

    def extract_image_text(self, path: Path) -> OcrResult:
        with Image.open(path) as image:
            text = pytesseract.image_to_string(image, lang=self.language)
        return OcrResult(text=clean_text(text), page_count=1)

    def extract_pdf_text(self, path: Path) -> OcrResult:
        chunks: list[str] = []
        with pymupdf.open(path) as document:
            matrix = pymupdf.Matrix(self.zoom, self.zoom)
            for page in document:
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
                chunks.append(pytesseract.image_to_string(image, lang=self.language))
            page_count = document.page_count
        return OcrResult(text=clean_text("\n\n".join(chunks)), page_count=page_count)
