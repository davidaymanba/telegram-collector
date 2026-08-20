from pathlib import Path

from app.config.settings import Settings


def test_settings_parse_supported_extensions_from_comma_string() -> None:
    settings = Settings(
        _env_file=None,
        supported_extensions="pdf, .PNG, jpg",
    )

    assert settings.supported_extensions == (".pdf", ".png", ".jpg")


def test_settings_expands_paths() -> None:
    settings = Settings(
        _env_file=None,
        storage_root="~/collector-storage",
    )

    assert settings.storage_root == Path("~/collector-storage").expanduser()


def test_require_telegram_credentials_raises_when_missing() -> None:
    settings = Settings(_env_file=None, telegram_api_id=None, telegram_api_hash=None)

    try:
        settings.require_telegram_credentials()
    except ValueError as exc:
        assert "TUC_TELEGRAM_API_ID" in str(exc)
    else:
        raise AssertionError("Expected missing Telegram credentials to raise ValueError")
