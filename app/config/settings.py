"""Environment-based application settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="TUC_",
        extra="ignore",
    )

    app_env: Literal["local", "test", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    database_url: str = (
        "mysql+pymysql://collector:collector-dev-password@127.0.0.1:3306/"
        "telegram_collector?charset=utf8mb4"
    )

    config_dir: Path = Path("config")
    channels_config_path: Path = Path("config/channels.yaml")
    subjects_config_path: Path = Path("config/subjects.yaml")

    storage_root: Path = Path("storage")
    incoming_storage_dir: Path = Path("storage/incoming")
    processed_storage_dir: Path = Path("storage/processed")
    unclassified_storage_dir: Path = Path("storage/unclassified")
    logs_dir: Path = Path("logs")
    lock_file_path: Path = Path("storage/collector.lock")

    telegram_api_id: int | None = None
    telegram_api_hash: SecretStr | None = None
    telegram_session_path: Path = Path("secrets/telegram.session")
    telegram_request_delay_seconds: float = Field(default=1.0, ge=0.2)
    telegram_collect_text_messages: bool = False

    supported_extensions: tuple[str, ...] = (
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".doc",
        ".docx",
        ".ppt",
        ".pptx",
    )

    ocr_enabled: bool = True
    ocr_language: str = "ara+eng"
    min_pdf_text_chars: int = Field(default=120, ge=0)
    max_classification_chars: int = Field(default=12_000, ge=1_000)

    ai_provider: Literal["none", "openai"] = "none"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4.1-mini"
    classification_min_confidence: float = Field(default=0.78, ge=0, le=1)
    classification_min_evidence_items: int = Field(default=1, ge=0)

    @field_validator(
        "config_dir",
        "channels_config_path",
        "subjects_config_path",
        "storage_root",
        "incoming_storage_dir",
        "processed_storage_dir",
        "unclassified_storage_dir",
        "logs_dir",
        "lock_file_path",
        "telegram_session_path",
        mode="before",
    )
    @classmethod
    def expand_user_path(cls, value: str | Path) -> Path:
        return Path(value).expanduser()

    @field_validator("supported_extensions", mode="before")
    @classmethod
    def parse_supported_extensions(
        cls,
        value: str | tuple[str, ...] | list[str],
    ) -> tuple[str, ...]:
        if isinstance(value, str):
            raw_items = [item.strip() for item in value.split(",")]
        else:
            raw_items = [str(item).strip() for item in value]

        extensions: list[str] = []
        for item in raw_items:
            if not item:
                continue
            normalized = item.lower()
            if not normalized.startswith("."):
                normalized = f".{normalized}"
            extensions.append(normalized)
        return tuple(dict.fromkeys(extensions))

    def require_telegram_credentials(self) -> None:
        """Raise a clear error when Telegram credentials are missing."""

        if self.telegram_api_id is None or self.telegram_api_hash is None:
            raise ValueError(
                "Telegram credentials are required. Set TUC_TELEGRAM_API_ID and "
                "TUC_TELEGRAM_API_HASH in the environment or .env file."
            )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for application entry points."""

    return Settings()
