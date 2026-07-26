"""Real DB, real DataFrame/COPY loading — only the network (the `statsapi`
package's own HTTP calls) is mocked, returning small fixture payloads shaped
like real statsapi.schedule()/standings_data()/get() output.

bootstrap()'s real range is 1901-present (125+ seasons) — far too slow and
fixture-heavy to actually loop in a test, so FIRST_SCHEDULE_YEAR/
FIRST_STANDINGS_YEAR are monkeypatched down to a 3-season window here. The
loop logic being exercised is identical either way."""

from datetime import date
from unittest.mock import patch

import pytest

from mlb_baseball.connectors import mlb_api

TABLES = ["raw.mlb_schedule", "raw.mlb_standing", "raw.mlb_live_game"]


def _game(game_id, season, status="Final", **overrides):
    game = {
        "game_id": game_id,
        "game_datetime": f"{season}-04-01T18:05:00Z",
        "game_date": f"{season}-04-01",
        "game_type": "R",
        "status": status,
        "away_name": "New York Yankees",
        "home_name": "Baltimore Orioles",
        "away_id": 147,
        "home_id": 110,
        "away_score": 2,
        "home_score": 5,
        "national_broadcasts": ["MLBN"],
        "winning_pitcher": "Someone",
        "losing_pitcher": "Someone Else",
        "save_pitcher": None,
    }
    game.update(overrides)
    return game


FIXTURE_GAMES_BY_SEASON = {
    2024: [_game(2001, 2024), _game(2002, 2024)],
    2025: [_game(2003, 2025)],
    2026: [_game(2004, 2026), _game(2005, 2026), _game(2006, 2026)],
}

FIXTURE_STANDINGS_BY_SEASON = {
    2024: {201: {"div_name": "AL East", "teams": [{"name": "Orioles", "team_id": 110, "w": 1}]}},
    2025: {201: {"div_name": "AL East", "teams": [{"name": "Orioles", "team_id": 110, "w": 2}]}},
    2026: {201: {"div_name": "AL East", "teams": [{"name": "Orioles", "team_id": 110, "w": 3}]}},
}


class _FixedDate(date):
    @classmethod
    def today(cls):
        return date(2026, 6, 1)


@pytest.fixture(autouse=True)
def _fixed_range(monkeypatch):
    monkeypatch.setattr(mlb_api, "date", _FixedDate)
    monkeypatch.setattr(mlb_api, "FIRST_SCHEDULE_YEAR", 2024)
    monkeypatch.setattr(mlb_api, "FIRST_STANDINGS_YEAR", 2024)


@pytest.fixture(autouse=True)
def _clean_tables(db_conn):
    yield
    with db_conn.cursor() as cur:
        for table in TABLES:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        # track_run() writes meta.ingestion_run rows that nothing else here
        # truncates — left alone, they'd accumulate across every test run in
        # the shared mlb_test database and make check_last_run("mlb_api")
        # unreliable for any test (this file's or another's) that asserts on
        # "never run" vs. "last run succeeded" (found via a real failure —
        # see test_doctor.py's mlb_api tests).
        cur.execute("DELETE FROM meta.ingestion_run WHERE source = %s", (mlb_api.SOURCE,))
    db_conn.commit()


def _mocked_schedule_and_standings():
    return patch.multiple(
        mlb_api.statsapi,
        schedule=lambda **kwargs: FIXTURE_GAMES_BY_SEASON.get(kwargs.get("season"), []),
        standings_data=lambda **kwargs: FIXTURE_STANDINGS_BY_SEASON.get(kwargs.get("season"), {}),
    )


def test_bootstrap_loads_full_history_across_multiple_seasons(db_conn):
    with _mocked_schedule_and_standings():
        counts = mlb_api.bootstrap()

    assert counts == {"raw.mlb_schedule": 6, "raw.mlb_standing": 3}
    with db_conn.cursor() as cur:
        cur.execute("SELECT _season, count(*) FROM raw.mlb_schedule GROUP BY _season ORDER BY 1")
        assert cur.fetchall() == [("2024", 2), ("2025", 1), ("2026", 3)]
        cur.execute("SELECT _season, w FROM raw.mlb_standing ORDER BY _season")
        assert cur.fetchall() == [("2024", "1"), ("2025", "2"), ("2026", "3")]


def test_bootstrap_skips_a_failing_season_and_continues(db_conn):
    def flaky_schedule(**kwargs):
        if kwargs.get("season") == 2025:
            raise RuntimeError("simulated transient API failure")
        return FIXTURE_GAMES_BY_SEASON.get(kwargs.get("season"), [])

    with (
        patch.object(mlb_api.statsapi, "schedule", side_effect=flaky_schedule),
        patch.object(mlb_api.statsapi, "standings_data", side_effect=lambda **k: {}),
    ):
        counts = mlb_api.bootstrap()

    # 2025's 1 game is missing, but 2024's 2 and 2026's 3 still landed.
    assert counts["raw.mlb_schedule"] == 5
    with db_conn.cursor() as cur:
        cur.execute("SELECT DISTINCT _season FROM raw.mlb_schedule ORDER BY 1")
        assert cur.fetchall() == [("2024",), ("2026",)]


def test_update_reloads_current_season_only_and_replaces_not_duplicates(db_conn):
    with _mocked_schedule_and_standings():
        mlb_api.bootstrap()
        mlb_api.update()

    with db_conn.cursor() as cur:
        cur.execute("SELECT _season, count(*) FROM raw.mlb_schedule GROUP BY _season ORDER BY 1")
        # Only 2026 (the "current" season under _FixedDate) gets touched again.
        assert cur.fetchall() == [("2024", 2), ("2025", 1), ("2026", 3)]


LIVE_GAME_FEED = {
    "gameData": {
        "status": {"abstractGameState": "Live", "detailedState": "In Progress"},
        "datetime": {"officialDate": "2026-06-01"},
        "teams": {"away": {"name": "Yankees"}, "home": {"name": "Orioles"}},
    },
    "liveData": {
        "linescore": {
            "currentInning": 5,
            "inningState": "Top",
            "teams": {
                "away": {"runs": 2, "hits": 4, "errors": 0},
                "home": {"runs": 1, "hits": 3, "errors": 1},
            },
            "offense": {"batter": {"id": 111, "fullName": "Batter One"}},
            "defense": {"pitcher": {"id": 222, "fullName": "Pitcher One"}},
            "balls": 1,
            "strikes": 2,
            "outs": 1,
        }
    },
}

FINAL_GAME_FEED = {
    "gameData": {"status": {"abstractGameState": "Final", "detailedState": "Final"}},
    "liveData": {"linescore": {}},
}


def test_capture_live_appends_snapshot_only_for_live_games(db_conn):
    schedule_today = [_game(3001, 2026), _game(3002, 2026)]

    def fake_get(endpoint, params, **kwargs):
        assert endpoint == "game"
        return LIVE_GAME_FEED if params["gamePk"] == 3001 else FINAL_GAME_FEED

    with (
        patch.object(mlb_api.statsapi, "schedule", return_value=schedule_today),
        patch.object(mlb_api.statsapi, "get", side_effect=fake_get),
    ):
        count = mlb_api.capture_live(db_conn)
    db_conn.commit()

    assert count == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT game_pk, current_inning, balls, strikes, outs, batter_name, pitcher_name "
            "FROM raw.mlb_live_game"
        )
        row = cur.fetchone()
    assert row == ("3001", "5", "1", "2", "1", "Batter One", "Pitcher One")


def test_capture_live_still_creates_the_table_when_nothing_is_live(db_conn):
    # Regression: the table's existence must not depend on the coincidence
    # of update() happening to run while a game is live — otherwise
    # check_table_exists reports a false "never bootstrapped?" on every
    # ordinary no-game-live day, as it did on the first real production run.
    schedule_today = [_game(3003, 2026)]
    with (
        patch.object(mlb_api.statsapi, "schedule", return_value=schedule_today),
        patch.object(mlb_api.statsapi, "get", return_value=FINAL_GAME_FEED),
    ):
        count = mlb_api.capture_live(db_conn)
    db_conn.commit()

    assert count == 0
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_live_game')")
        assert cur.fetchone() == ("raw.mlb_live_game",)
        cur.execute("SELECT count(*) FROM raw.mlb_live_game")
        assert cur.fetchone() == (0,)


def test_capture_live_appends_across_calls_instead_of_replacing(db_conn):
    schedule_today = [_game(3004, 2026)]
    with (
        patch.object(mlb_api.statsapi, "schedule", return_value=schedule_today),
        patch.object(mlb_api.statsapi, "get", return_value=LIVE_GAME_FEED),
    ):
        mlb_api.capture_live(db_conn)  # snapshot 1: bottom of the 5th, so to speak
        mlb_api.capture_live(db_conn)  # snapshot 2: same game, captured again later
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.mlb_live_game WHERE game_pk = '3004'")
        assert cur.fetchone() == (2,)  # both snapshots kept, not overwritten


def test_update_includes_live_capture_count(db_conn):
    with (
        _mocked_schedule_and_standings(),
        patch.object(mlb_api.statsapi, "get", return_value=FINAL_GAME_FEED),
    ):
        counts = mlb_api.update()

    assert counts == {"raw.mlb_schedule": 3, "raw.mlb_standing": 1, "raw.mlb_live_game": 0}


def test_health_check_reports_healthy_with_zero_live_rows(db_conn):
    # check_table_exists (not check_table_has_rows) backs raw.mlb_live_game
    # specifically because 0 rows there is a normal, healthy state — nothing
    # live right now isn't the same as "never bootstrapped."
    with (
        _mocked_schedule_and_standings(),
        patch.object(mlb_api.statsapi, "get", return_value=FINAL_GAME_FEED),
    ):
        mlb_api.bootstrap()
        mlb_api.update()  # creates raw.mlb_live_game via capture_live, 0 rows today
    db_conn.commit()

    checks = mlb_api.health_check()

    live_check = next(c for c in checks if c.name == "raw.mlb_live_game")
    assert live_check.ok
    assert "0 rows" in live_check.detail
