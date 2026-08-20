import json
import logging

from app.config.settings import Settings
from app.logging.setup import JsonFormatter, configure_logging


def test_json_formatter_redacts_sensitive_extra_fields() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="login event",
        args=(),
        exc_info=None,
    )
    record.api_hash = "secret-value"
    record.session_path = "secrets/telegram.session"
    record.channel_name = "database"

    payload = json.loads(formatter.format(record))

    assert payload["api_hash"] == "***REDACTED***"
    assert payload["session_path"] == "***REDACTED***"
    assert payload["channel_name"] == "database"


def test_configure_logging_sets_root_level() -> None:
    settings = Settings(_env_file=None, log_level="DEBUG", log_format="console")

    configure_logging(settings)

    assert logging.getLogger().level == logging.DEBUG
