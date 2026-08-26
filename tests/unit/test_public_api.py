import os

import pytest

import mlb_baseball as mlb
from mlb_baseball import public
from mlb_baseball.source_profiles import SourceProfileError


def test_top_level_exports_are_the_supported_public_api():
    assert set(mlb.__all__) == {
        "SourceProfileError",
        "build_features",
        "configure",
        "conform_database",
        "get_connection",
        "health_checks",
        "ingest_source",
        "inventory_runs",
        "inventory_tables",
        "migrate_database",
        "run_predictions",
    }
    assert not hasattr(mlb, "_acquire_source_lock")
    assert not hasattr(mlb, "load_dataframe")


def test_configure_sets_only_process_local_values():
    # configure() writes directly to os.environ (that's the behavior under
    # test). monkeypatch.setenv/delenv can't be relied on to undo that
    # afterward: it restores each key to whatever os.environ held right
    # before *its own* call, but configure()'s direct assignment happens
    # between the delenv calls below and any monkeypatch call that could
    # re-capture it, so nothing monkeypatch does actually reverts it. That
    # was tried here first and confirmed, empirically, not to work --
    # DATABASE_URL/MLB_DATA_PROFILE kept leaking process-wide for the rest
    # of the pytest session (a real, previously unnoticed test-isolation
    # bug: only surfaces when another module's tests run afterward in the
    # same process -- e.g. tests/unit/test_cli_dispatch.py's ingest-dispatch
    # tests start failing with "forbidden by the public_safe data profile"
    # once this test has run first). Found by running Plan 01's
    # acceptance-gate tests together for 01F-R6 rather than one file at a
    # time. conftest.py's own DATABASE_URL=mlb_test override makes the
    # leaked value harmless here, but leaking it at all violates this
    # repo's own test-isolation rule -- fixed with a plain try/finally that
    # saves and restores the real os.environ entries directly, independent
    # of monkeypatch's undo-stack semantics.
    had_database_url = "DATABASE_URL" in os.environ
    original_database_url = os.environ.get("DATABASE_URL")
    had_profile = "MLB_DATA_PROFILE" in os.environ
    original_profile = os.environ.get("MLB_DATA_PROFILE")
    try:
        mlb.configure(database_url="postgresql:///research", profile="public_safe")

        assert public.os.environ["DATABASE_URL"] == "postgresql:///research"
        assert public.os.environ["MLB_DATA_PROFILE"] == "public_safe"
    finally:
        if had_database_url:
            os.environ["DATABASE_URL"] = original_database_url
        else:
            os.environ.pop("DATABASE_URL", None)
        if had_profile:
            os.environ["MLB_DATA_PROFILE"] = original_profile
        else:
            os.environ.pop("MLB_DATA_PROFILE", None)


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
