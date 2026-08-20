"""Conservative text normalization before classification."""

from __future__ import annotations

import re
import unicodedata

_HORIZONTAL_WHITESPACE = re.compile(r"[ \t\f\v]+")
_MANY_BLANK_LINES = re.compile(r"\n{3,}")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(text: str) -> str:
    """Normalize whitespace and control characters without destroying content."""

    normalized = unicodedata.normalize("NFKC", text)
    normalized = _CONTROL_CHARS.sub(" ", normalized)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(
        _HORIZONTAL_WHITESPACE.sub(" ", line).strip() for line in normalized.split("\n")
    )
    normalized = _MANY_BLANK_LINES.sub("\n\n", normalized)
    return normalized.strip()


def truncate_for_classification(text: str, max_chars: int) -> str:
    """Limit text sent to an AI provider with a deterministic head/tail sample."""

    if len(text) <= max_chars:
        return text

    head_size = max_chars // 2
    tail_size = max_chars - head_size
    return f"{text[:head_size]}\n\n[...TRUNCATED...]\n\n{text[-tail_size:]}"
