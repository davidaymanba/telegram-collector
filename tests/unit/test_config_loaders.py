from pathlib import Path

import pytest

from app.config.loaders import (
    ContentType,
    allowed_content_type_values,
    load_channels_config,
    load_subjects_config,
)


def test_load_channels_config_returns_enabled_channels(tmp_path: Path) -> None:
    config_path = tmp_path / "channels.yaml"
    config_path.write_text(
        """
channels:
  - name: database
    username: "@database_channel"
    enabled: true
  - name: disabled
    username: "https://t.me/disabled_channel"
    enabled: false
""",
        encoding="utf-8",
    )

    config = load_channels_config(config_path)

    assert [channel.name for channel in config.enabled_channels] == ["database"]


def test_load_channels_config_rejects_invalid_username(tmp_path: Path) -> None:
    config_path = tmp_path / "channels.yaml"
    config_path.write_text(
        """
channels:
  - name: database
    username: "database_channel"
    enabled: true
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="channel username"):
        load_channels_config(config_path)


def test_load_channels_config_rejects_duplicate_names(tmp_path: Path) -> None:
    config_path = tmp_path / "channels.yaml"
    config_path.write_text(
        """
channels:
  - name: database
    username: "@database_one"
  - name: database
    username: "@database_two"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="channel names must be unique"):
        load_channels_config(config_path)


def test_load_subjects_config_normalizes_codes(tmp_path: Path) -> None:
    config_path = tmp_path / "subjects.yaml"
    config_path.write_text(
        """
subjects:
  - code: db101
    name_ar: "قواعد البيانات"
    name_en: "Database"
""",
        encoding="utf-8",
    )

    config = load_subjects_config(config_path)

    assert config.subject_codes == {"DB101"}


def test_allowed_content_types_are_stable() -> None:
    assert allowed_content_type_values() == {
        ContentType.LECTURE.value,
        ContentType.PREVIOUS_EXAM.value,
        ContentType.ASSIGNMENT.value,
        ContentType.ANSWER_MODEL.value,
        ContentType.SUMMARY.value,
    }
