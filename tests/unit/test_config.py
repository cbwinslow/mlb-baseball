import pytest

from mlb_baseball import config


def test_database_url_missing_raises(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        config.database_url()


def test_database_url_returns_value(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    assert config.database_url() == "postgresql://u:p@localhost/db"
