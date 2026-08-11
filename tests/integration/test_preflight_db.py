"""Preflight touches the real disposable database but never mutates it."""

import os

from mlb_baseball import preflight
from mlb_baseball.config import Settings


def test_preflight_reports_migrated_test_database(db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(preflight.chadwick_tools, "missing_tools", lambda: [])
    settings = Settings(
        database_url=os.environ["DATABASE_URL"],
        test_database_url=None,
        download_dir=tmp_path / "downloads",
        log_dir=tmp_path / "logs",
        analytics_workers=8,
        analytics_start_year=1950,
        analytics_end_year=None,
        retry_attempts=3,
        backoff_seconds=1.0,
        request_timeout_seconds=5,
    )

    checks, commands = preflight.run(settings, ["mlb_api"], with_conform=False)

    database = next(check for check in checks if check.name == "database")
    assert database.ok
    assert database.detail == "reachable; migrations current"
    assert commands[0] == "mlb migrate"
