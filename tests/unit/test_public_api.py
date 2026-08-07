import pytest

import mlb_baseball as mlb
from mlb_baseball import public
from mlb_baseball.source_profiles import SourceProfileError


def test_top_level_exports_are_the_supported_public_api():
    assert set(mlb.__all__) == {
        "SourceProfileError",
        "configure",
        "conform_database",
        "get_connection",
        "health_checks",
        "ingest_source",
        "inventory_runs",
        "inventory_tables",
        "migrate_database",
    }
    assert not hasattr(mlb, "_acquire_source_lock")
    assert not hasattr(mlb, "load_dataframe")


def test_configure_sets_only_process_local_values(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("MLB_DATA_PROFILE", raising=False)

    mlb.configure(database_url="postgresql:///research", profile="public_safe")

    assert public.os.environ["DATABASE_URL"] == "postgresql:///research"
    assert public.os.environ["MLB_DATA_PROFILE"] == "public_safe"


def test_ingest_source_rejects_source_outside_profile(monkeypatch):
    monkeypatch.setenv("MLB_DATA_PROFILE", "public_safe")

    with pytest.raises(SourceProfileError, match="mlb_api"):
        mlb.ingest_source("mlb_api")


def test_ingest_source_dispatches_selected_mode(monkeypatch):
    calls = []
    fake = type(
        "FakeConnector",
        (),
        {"update": staticmethod(lambda: calls.append("update") or {"raw.x": 1})},
    )
    monkeypatch.setattr(public, "CONNECTORS", {"fake": fake})

    assert mlb.ingest_source("fake", mode="update", profile="local_research") == {"raw.x": 1}
    assert calls == ["update"]
