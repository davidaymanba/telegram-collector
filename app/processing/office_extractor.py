"""Text extraction for modern Office documents without external services."""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree

from app.processing.text_cleaner import clean_text


def _xml_text_from_zip(path: Path, member_prefix: str, member_suffix: str = ".xml") -> str:
    chunks: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for member in sorted(archive.namelist()):
            if not member.startswith(member_prefix) or not member.endswith(member_suffix):
                continue
            root = ElementTree.fromstring(archive.read(member))
            for element in root.iter():
                if element.text and element.tag.endswith("}t"):
                    chunks.append(element.text)
    return clean_text("\n".join(chunks))


def extract_docx_text(path: Path) -> str:
    return _xml_text_from_zip(path, "word/")


def extract_pptx_text(path: Path) -> str:
    return _xml_text_from_zip(path, "ppt/slides/")
