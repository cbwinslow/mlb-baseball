"""Real DB, real DataFrame/COPY loading — only the network (statsapi's own
HTTP calls) is mocked."""

from datetime import date
from unittest.mock import patch

import pytest

from mlb_baseball.connectors import mlb_api_extra as extra

TABLES = [
    "raw.mlb_sport",
    "raw.mlb_league",
    "raw.mlb_division",
    "raw.mlb_season",
    "raw.mlb_player_pool",
    "raw.mlb_free_agent",
    "raw.mlb_coach",
    "raw.mlb_alumni",
    "raw.mlb_personnel",
    "raw.mlb_affiliate",
    "raw.mlb_attendance",
    "raw.mlb_game_pace",
]

FIXTURE_TEAMS = {"teams": [{"id": 110}]}


def _fake_get(endpoint, params=None, **kwargs):
    params = params or {}
    if endpoint == "teams":
        return FIXTURE_TEAMS
    if endpoint == "sports":
        return {"sports": [{"id": 1, "code": "mlb", "name": "Major League Baseball"}]}
    if endpoint == "league":
        return {"leagues": [{"id": 103, "name": "American League", "seasonDateInfo": {}}]}
    if endpoint == "divisions":
        return {"divisions": [{"id": 200, "name": "AL West", "league": {"id": 103}}]}
    if endpoint == "seasons":
        return {"seasons": [{"seasonId": "2024"}]}
    if endpoint == "sports_players":
        return {"people": [{"id": 1, "fullName": "Player One", "currentTeam": {"id": 110}}]}
    if endpoint == "people_freeAgents":
        return {"freeAgents": [{"player": {"id": 1, "fullName": "Player One"}}]}
    if endpoint == "team_coaches":
        return {"roster": [{"person": {"id": 2, "fullName": "Coach One"}, "job": "Manager"}]}
    if endpoint == "team_alumni":
        return {"people": [{"id": 3, "fullName": "Alum One"}]}
    if endpoint == "team_personnel":
        return {"roster": [{"person": {"id": 4, "fullName": "Staffer One"}, "job": "GM"}]}
    if endpoint == "teams_affiliates":
        return {"teams": [{"id": 500, "name": "Farm Team", "league": {}, "sport": {}}]}
    if endpoint == "attendance":
        return {"records": [{"year": "2024", "gamesTotal": 81}]}
    if endpoint == "gamePace":
        return {"sports": [{"hitsPer9Inn": 16.0}]}
    raise AssertionError(f"unexpected endpoint: {endpoint}")


class _FixedDate(date):
    @classmethod
    def today(cls):
        return date(2026, 6, 1)


@pytest.fixture(autouse=True)
def _fixed_range(monkeypatch):
    monkeypatch.setattr(extra, "date", _FixedDate)
    monkeypatch.setattr(extra, "FIRST_YEAR", 2024)


@pytest.fixture(autouse=True)
def _clean_tables(db_conn):
    yield
    with db_conn.cursor() as cur:
        for table in TABLES:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute("DELETE FROM meta.ingestion_run WHERE source = %s", (extra.SOURCE,))
    db_conn.commit()


def _mocked_statsapi():
    return patch.object(extra.statsapi, "get", side_effect=_fake_get)


def test_bootstrap_loads_every_table(db_conn):
    with _mocked_statsapi():
        counts = extra.bootstrap()

    for table in [
        "raw.mlb_player_pool",
        "raw.mlb_free_agent",
        "raw.mlb_coach",
        "raw.mlb_alumni",
        "raw.mlb_game_pace",
        "raw.mlb_sport",
        "raw.mlb_league",
        "raw.mlb_division",
        "raw.mlb_season",
        "raw.mlb_personnel",
        "raw.mlb_affiliate",
        "raw.mlb_attendance",
    ]:
        assert counts[table] > 0, f"{table} should have loaded rows"

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.mlb_player_pool")
        assert cur.fetchone() == (3,)  # 2024, 2025, 2026 (FIRST_YEAR monkeypatched to 2024)


def test_bootstrap_is_idempotent(db_conn):
    with _mocked_statsapi():
        extra.bootstrap()
        extra.bootstrap()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.mlb_sport")
        assert cur.fetchone() == (1,)
        cur.execute("SELECT count(*) FROM raw.mlb_attendance")
        assert cur.fetchone() == (1,)


def test_bootstrap_skips_a_failing_season_and_continues(db_conn):
    def flaky_get(endpoint, params=None, **kwargs):
        params = params or {}
        if endpoint == "sports_players" and params.get("season") == 2025:
            raise RuntimeError("simulated transient API failure")
        return _fake_get(endpoint, params, **kwargs)

    with patch.object(extra.statsapi, "get", side_effect=flaky_get):
        counts = extra.bootstrap()

    assert counts["raw.mlb_player_pool"] == 2  # 2024 and 2026 landed; 2025's whole season failed
    with db_conn.cursor() as cur:
        cur.execute("SELECT DISTINCT _season FROM raw.mlb_player_pool ORDER BY 1")
        assert cur.fetchall() == [("2024",), ("2026",)]


def test_update_touches_current_season_only(db_conn):
    with _mocked_statsapi():
        extra.bootstrap()
        counts = extra.update()

    assert counts["raw.mlb_player_pool"] > 0
    with db_conn.cursor() as cur:
        cur.execute("SELECT DISTINCT _season FROM raw.mlb_player_pool ORDER BY 1")
        assert cur.fetchall() == [("2024",), ("2025",), ("2026",)]


def test_health_check_reports_last_run_not_freshness(db_conn):
    with _mocked_statsapi():
        extra.bootstrap()

    checks = extra.health_check()

    assert any(c.name == f"{extra.SOURCE} last run" for c in checks)
    assert not any(c.name == f"{extra.SOURCE} freshness" for c in checks)
    assert all(c.ok for c in checks)
