from pathlib import Path

from app.cli.commands import main
from app.config.settings import Settings
from app.database.models import ProcessingRun
from app.database.session import create_database_engine, create_session_factory


def test_cli_health_init_and_report_with_temp_config(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    channels_path = tmp_path / "channels.yaml"
    subjects_path = tmp_path / "subjects.yaml"
    storage_root = tmp_path / "storage"
    channels_path.write_text(
        """
channels:
  - name: database
    username: "@database_channel"
    enabled: true
""",
        encoding="utf-8",
    )
    subjects_path.write_text(
        """
subjects:
  - code: DB101
    name_ar: "قواعد البيانات"
    name_en: "Database"
""",
        encoding="utf-8",
    )

    monkeypatch.setenv("TUC_DATABASE_URL", f"sqlite:///{tmp_path / 'cli.db'}")
    monkeypatch.setenv("TUC_CHANNELS_CONFIG_PATH", str(channels_path))
    monkeypatch.setenv("TUC_SUBJECTS_CONFIG_PATH", str(subjects_path))
    monkeypatch.setenv("TUC_STORAGE_ROOT", str(storage_root))
    monkeypatch.setenv("TUC_INCOMING_STORAGE_DIR", str(storage_root / "incoming"))
    monkeypatch.setenv("TUC_PROCESSED_STORAGE_DIR", str(storage_root / "processed"))
    monkeypatch.setenv("TUC_UNCLASSIFIED_STORAGE_DIR", str(storage_root / "unclassified"))
    monkeypatch.setenv("TUC_LOCK_FILE_PATH", str(storage_root / "collector.lock"))

    assert main(["health-check"]) == 0
    assert main(["init-db"]) == 0
    assert main(["seed-demo"]) == 0
    assert main(["process"]) == 0
    assert main(["report"]) == 0

    output = capsys.readouterr().out
    assert "Run Report" in output
    assert "DB101" in output

    settings = Settings(_env_file=None)
    session_factory = create_session_factory(create_database_engine(settings))
    with session_factory() as session:
        assert session.query(ProcessingRun).count() == 2
