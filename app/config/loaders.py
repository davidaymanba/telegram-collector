"""YAML configuration loaders for channels, subjects, and content types."""

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ContentType(StrEnum):
    """Stable internal content type values."""

    LECTURE = "lecture"
    PREVIOUS_EXAM = "previous_exam"
    ASSIGNMENT = "assignment"
    ANSWER_MODEL = "answer_model"
    SUMMARY = "summary"


CONTENT_TYPE_LABELS: dict[ContentType, dict[str, str]] = {
    ContentType.LECTURE: {"ar": "محاضرة", "en": "Lecture"},
    ContentType.PREVIOUS_EXAM: {"ar": "امتحان سابق", "en": "Previous exam"},
    ContentType.ASSIGNMENT: {"ar": "تكليف", "en": "Assignment"},
    ContentType.ANSWER_MODEL: {"ar": "نموذج إجابة", "en": "Answer model"},
    ContentType.SUMMARY: {"ar": "ملخص", "en": "Summary"},
}


class ChannelConfig(BaseModel):
    """One Telegram channel entry loaded from config/channels.yaml."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    username: str = Field(min_length=1)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("channel name cannot be empty")
        return normalized

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        normalized = value.strip()
        if normalized.startswith("@") or normalized.startswith("https://t.me/"):
            return normalized
        raise ValueError("channel username must start with '@' or 'https://t.me/'")


class ChannelsConfig(BaseModel):
    """Root model for all channel configuration."""

    model_config = ConfigDict(extra="forbid")

    channels: list[ChannelConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_names(self) -> "ChannelsConfig":
        names = [channel.name for channel in self.channels]
        if len(names) != len(set(names)):
            raise ValueError("channel names must be unique")
        return self

    @property
    def enabled_channels(self) -> list[ChannelConfig]:
        return [channel for channel in self.channels if channel.enabled]


class SubjectConfig(BaseModel):
    """Allowed subject definition used by the classifier validator."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=2, max_length=32)
    name_ar: str = Field(min_length=1)
    name_en: str = Field(min_length=1)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized.replace("_", "").replace("-", "").isalnum():
            raise ValueError(
                "subject code must contain only letters, numbers, underscores, or hyphens"
            )
        if not normalized[0].isalnum():
            raise ValueError("subject code must start with a letter or number")
        return normalized

    @field_validator("name_ar", "name_en")
    @classmethod
    def strip_names(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("subject names cannot be empty")
        return normalized


class SubjectsConfig(BaseModel):
    """Root model for all allowed subject configuration."""

    model_config = ConfigDict(extra="forbid")

    subjects: list[SubjectConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_subjects(self) -> "SubjectsConfig":
        codes = [subject.code for subject in self.subjects]
        if len(codes) != len(set(codes)):
            raise ValueError("subject codes must be unique")
        return self

    @property
    def subject_codes(self) -> set[str]:
        return {subject.code for subject in self.subjects}


def load_yaml_file(path: Path) -> dict[str, Any]:
    """Read a YAML document and ensure the root value is a mapping."""

    if not path.exists():
        raise FileNotFoundError(f"Configuration file does not exist: {path}")

    with path.open("r", encoding="utf-8") as file_obj:
        data = yaml.safe_load(file_obj) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Configuration root must be a mapping: {path}")
    return data


def load_channels_config(path: str | Path) -> ChannelsConfig:
    """Load and validate Telegram channel configuration."""

    return ChannelsConfig.model_validate(load_yaml_file(Path(path)))


def load_subjects_config(path: str | Path) -> SubjectsConfig:
    """Load and validate allowed subject configuration."""

    return SubjectsConfig.model_validate(load_yaml_file(Path(path)))


def allowed_content_type_values() -> set[str]:
    """Return content type values the classifier is allowed to emit."""

    return {content_type.value for content_type in ContentType}
