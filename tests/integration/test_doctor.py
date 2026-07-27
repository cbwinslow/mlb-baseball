"""doctor.run()'s per-check logic is tested against the real (empty but
migrated) test database. The connector-aggregation loop is tested with a
faked CONNECTORS registry — real lahman/retrosheet tables only exist in the
production database (populated by running the actual connectors, which is
not something the fast test suite should depend on)."""

import uuid
from unittest.mock import patch

import psycopg

from mlb_baseball import doctor
from mlb_baseball.connectors import mlb_api
from mlb_baseball.health import Check


def test_database_reachable_is_true_against_the_test_db():
    assert doctor._database_reachable().ok


def test_required_schemas_exist_against_the_test_db():
    result = doctor._required_schemas_exist()
    assert result.ok
    for schema in doctor._REQUIRED_SCHEMAS:
        assert schema in result.detail


def test_migrations_up_to_date_against_the_test_db():
    # The session fixture in conftest.py already applied every migration.
    assert doctor._migrations_up_to_date().ok


def test_migrations_up_to_date_reports_actionable_message_on_unmigrated_db(monkeypatch):
    # Regression: a genuinely fresh clone's database is reachable but has
    # never had `mlb migrate` run — public.schema_migrations doesn't exist
    # yet. This used to crash doctor with a raw UndefinedTable traceback
    # instead of reporting it as a clean, actionable failed check. Can't
    # safely test this against the shared mlb_test database (every other
    # test in this suite assumes it's already migrated), so this spins up a
    # genuinely separate, disposable database instead.
    db_name = f"mlb_doctor_freshtest_{uuid.uuid4().hex[:8]}"
    with psycopg.connect("postgresql:///postgres", autocommit=True) as admin_conn:
        with admin_conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE {db_name}")
        try:
            monkeypatch.setenv("DATABASE_URL", f"postgresql:///{db_name}")
            result = doctor._migrations_up_to_date()
        finally:
            with admin_conn.cursor() as cur:
                cur.execute(f"DROP DATABASE {db_name}")

    assert not result.ok
    assert "mlb migrate" in result.detail


def test_run_includes_a_fake_connectors_health_checks(monkeypatch):
    fake = type(
        "FakeConnector",
        (),
        {"health_check": staticmethod(lambda: [Check("fake thing", True, "looks fine")])},
    )
    monkeypatch.setattr(doctor, "CONNECTORS", {"fake": fake})

    checks = doctor.run()

    assert any(c.name == "fake thing" and c.ok for c in checks)


def test_run_flags_a_connector_with_no_health_check(monkeypatch):
    fake = type("FakeConnector", (), {})  # deliberately no health_check
    monkeypatch.setattr(doctor, "CONNECTORS", {"fake": fake})

    checks = doctor.run()

    match = next(c for c in checks if c.name == "fake connector")
    assert not match.ok
    assert "no health_check" in match.detail


def test_run_survives_a_connector_whose_health_check_raises(monkeypatch):
    # A never-bootstrapped connector querying a table that doesn't exist yet
    # (or any other health_check() bug) must not blind doctor to every other
    # connector's health — it should be reported as one failed check, not
    # crash the whole run.
    def _broken():
        raise RuntimeError("boom")

    broken = type("BrokenConnector", (), {"health_check": staticmethod(_broken)})
    fine = type(
        "FineConnector",
        (),
        {"health_check": staticmethod(lambda: [Check("fine thing", True, "looks fine")])},
    )
    monkeypatch.setattr(doctor, "CONNECTORS", {"broken": broken, "fine": fine})

    checks = doctor.run()

    broken_check = next(c for c in checks if c.name == "broken connector")
    assert not broken_check.ok
    assert "boom" in broken_check.detail
    assert any(c.name == "fine thing" and c.ok for c in checks)


def test_run_diagnoses_mlb_api_cleanly_before_it_has_ever_been_bootstrapped(db_conn, monkeypatch):
    # End-to-end, against the real (test) database, not a fake connector:
    # a fresh clone that's run `mlb migrate` but never `mlb ingest mlb_api`
    # must get clean, actionable failed checks through the real doctor.run()
    # path — not a crash, and not a false "all clear."
    monkeypatch.setattr(doctor, "CONNECTORS", {"mlb_api": mlb_api})
    # Guarantee a genuinely "never run" state regardless of what any earlier
    # test (in this file or another) already wrote to meta.ingestion_run —
    # that table is a durable audit log nothing else truncates.
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM meta.ingestion_run WHERE source = %s", (mlb_api.SOURCE,))
    db_conn.commit()

    checks = doctor.run()

    schedule_check = next(c for c in checks if c.name == "raw.mlb_schedule")
    assert not schedule_check.ok
    live_check = next(c for c in checks if c.name == "raw.mlb_live_game")
    assert not live_check.ok  # table doesn't exist yet either — also a clean failure
    run_check = next(c for c in checks if c.name == "mlb_api freshness")
    assert not run_check.ok
    assert "never run" in run_check.detail


def test_run_diagnoses_mlb_api_as_healthy_after_bootstrap_including_empty_live_table(
    db_conn, monkeypatch
):
    monkeypatch.setattr(doctor, "CONNECTORS", {"mlb_api": mlb_api})
    monkeypatch.setattr(mlb_api, "FIRST_SCHEDULE_YEAR", 2026)
    monkeypatch.setattr(mlb_api, "FIRST_STANDINGS_YEAR", 2026)
    monkeypatch.setattr(mlb_api, "FIRST_ROSTER_YEAR", 2026)
    monkeypatch.setattr(mlb_api, "FIRST_TRANSACTION_YEAR", 2026)
    monkeypatch.setattr(mlb_api, "FIRST_PLAYBYPLAY_YEAR", 2026)
    games = [{"game_id": 1, "national_broadcasts": [], "winning_team": "Tie", "status": "Final"}]
    standings = {201: {"div_name": "AL East", "teams": [{"name": "Orioles", "team_id": 110}]}}

    def fake_get(endpoint, params=None, **kwargs):
        if endpoint == "teams":
            return {"teams": [{"id": 110}]}
        if endpoint == "team_roster":
            return {"roster": []}
        if endpoint == "transactions":
            return {"transactions": []}
        if endpoint == "game_playByPlay":
            return {"allPlays": []}
        raise AssertionError(f"unexpected endpoint: {endpoint}")

    with (
        patch.object(mlb_api.statsapi, "schedule", return_value=games),
        patch.object(mlb_api.statsapi, "standings_data", return_value=standings),
        patch.object(mlb_api.statsapi, "get", side_effect=fake_get),
    ):
        mlb_api.bootstrap()

    checks = doctor.run()

    assert next(c for c in checks if c.name == "raw.mlb_schedule").ok
    assert next(c for c in checks if c.name == "raw.mlb_standing").ok
    # raw.mlb_live_game was never created (no live games during bootstrap) —
    # check_table_exists must not treat that as unhealthy the way
    # check_table_has_rows would.
    live_check = next(c for c in checks if c.name == "raw.mlb_live_game")
    assert not live_check.ok
    assert "never bootstrapped" in live_check.detail
    assert next(c for c in checks if c.name == "mlb_api freshness").ok

    with db_conn.cursor() as cur:
        for table in [
            "raw.mlb_schedule",
            "raw.mlb_standing",
            "raw.mlb_roster",
            "raw.mlb_transaction",
            "raw.mlb_playbyplay",
        ]:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute("DELETE FROM meta.ingestion_run WHERE source = %s", (mlb_api.SOURCE,))
    db_conn.commit()
