"""Safe file-name and storage path helpers."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(filename: str, *, fallback: str = "file") -> str:
    """Return a path-safe ASCII filename."""

    normalized = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.replace("/", "_").replace("\\", "_")
    normalized = _UNSAFE_FILENAME_CHARS.sub("_", normalized).strip("._")
    if not normalized:
        normalized = fallback
    return normalized[:180]


def ensure_child_path(root: Path, child: Path) -> Path:
    """Ensure `child` resolves under `root` to prevent path traversal."""

    resolved_root = root.resolve()
    resolved_child = child.resolve()
    if resolved_root != resolved_child and resolved_root not in resolved_child.parents:
        raise ValueError(f"Path is outside storage root: {child}")
    return resolved_child


def incoming_file_path(root: Path, channel_name: str, message_id: int, filename: str) -> Path:
    channel_dir = root / safe_filename(channel_name, fallback="channel")
    safe_name = safe_filename(filename, fallback=f"message_{message_id}")
    return channel_dir / f"{message_id}_{safe_name}"
