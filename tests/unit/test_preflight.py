from mlb_baseball import preflight
from mlb_baseball.config import Settings


def _settings(tmp_path, database_url=None):
    return Settings(
        database_url=database_url,
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


def test_preflight_plans_without_running_connectors(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight.chadwick_tools, "missing_tools", lambda: [])
    settings = _settings(tmp_path)

    checks, commands = preflight.run(settings, ["mlb_api"], with_conform=True)

    assert any(check.name == "database" and not check.ok for check in checks)
    assert commands == [
        "mlb migrate",
        "mlb ingest mlb_api --mode bootstrap",
        "mlb conform  # only after raw-layer doctor checks are healthy",
        "mlb doctor",
        "mlb inventory",
    ]
    assert settings.download_dir.exists()
    assert settings.log_dir.exists()


def test_preflight_does_not_expose_database_url_in_a_failure(tmp_path):
    secret_url = "postgresql://user:very-secret-password@not-a-host/mlb"
    checks, _ = preflight.run(_settings(tmp_path, secret_url), [], with_conform=False)

    database = next(check for check in checks if check.name == "database")
    assert "very-secret-password" not in database.detail
