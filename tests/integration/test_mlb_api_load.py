"""Real DB, real DataFrame/COPY loading — only the network (the `statsapi`
package's own HTTP calls) is mocked, returning small fixture payloads shaped
like real statsapi output.

bootstrap()'s real range is 1901-present (125+ seasons) for schedule/
standings/rosters/transactions, and 2026-present (per-game) for play-by-play
— far too slow and fixture-heavy to actually loop in a test, so every
FIRST_*_YEAR constant is monkeypatched down to a tiny window here. The loop
logic being exercised is identical either way."""

from datetime import date
from unittest.mock import patch

import pytest

from mlb_baseball.connectors import mlb_api

TABLES = [
    "raw.mlb_schedule",
    "raw.mlb_standing",
    "raw.mlb_roster",
    "raw.mlb_transaction",
    "raw.mlb_playbyplay",
    "raw.mlb_live_game",
    "raw.mlb_venue",
    "raw.mlb_team_history",
    "raw.mlb_person",
    "raw.mlb_draft",
    "raw.mlb_boxscore_batting",
    "raw.mlb_boxscore_pitching",
    "raw.mlb_boxscore_fielding",
    "raw.mlb_umpire",
    "raw.mlb_win_prob",
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
    "raw.mlb_player_stat",
    "raw.mlb_team_stat",
    "raw.mlb_stat_leader",
    "raw.mlb_team_leader",
    "raw.mlb_award",
]


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

FIXTURE_TEAMS = {"teams": [{"id": 110}]}
FIXTURE_ROSTER = {
    "roster": [
        {
            "person": {"id": 1, "fullName": "Player One"},
            "jerseyNumber": "10",
            "position": {"code": "1", "name": "Pitcher", "type": "Pitcher"},
            "status": {"code": "A", "description": "Active"},
        }
    ]
}
FIXTURE_TRANSACTIONS = {
    "transactions": [
        {
            "id": 1,
            "person": {"id": 1, "fullName": "Player One"},
            "toTeam": {"id": 110, "name": "Orioles"},
            "date": "2024-01-01",
            "typeCode": "SC",
            "typeDesc": "Status Change",
            "description": "Activated.",
        }
    ]
}
FIXTURE_PLAYBYPLAY = {
    "allPlays": [
        {
            "atBatIndex": 0,
            "about": {"inning": 1, "halfInning": "top"},
            "count": {"balls": 0, "strikes": 0, "outs": 1},
            "matchup": {
                "batter": {"id": 1, "fullName": "Player One"},
                "pitcher": {"id": 2, "fullName": "Player Two"},
            },
            "result": {"event": "Groundout", "eventType": "field_out", "description": "Groundout."},
        }
    ]
}

FIXTURE_VENUE_IDS = {"venues": [{"id": 100}]}
FIXTURE_VENUE_DETAIL = {
    "venues": [
        {
            "id": 100,
            "name": "Test Park",
            "active": True,
            "location": {"city": "Springfield"},
            "timeZone": {"id": "America/Chicago"},
            "fieldInfo": {"capacity": 5000},
        }
    ]
}
FIXTURE_TEAM_HISTORY = {
    "teams": [
        {
            "id": 110,
            "season": 1954,
            "name": "Baltimore Orioles",
            "venue": {"id": 100, "name": "Test Park"},
            "league": {"name": "American League"},
        }
    ]
}
FIXTURE_PEOPLE = {
    "people": [
        {
            "id": 1,
            "fullName": "Player One",
            "birthDate": "2000-01-01",
            "primaryPosition": {"code": "1", "name": "Pitcher"},
        }
    ]
}
FIXTURE_DRAFT = {
    "drafts": {
        "rounds": [
            {
                "picks": [
                    {
                        "pickRound": "1",
                        "pickNumber": 1,
                        "person": {"id": 1, "fullName": "Player One"},
                        "team": {"id": 110, "name": "Orioles"},
                        "home": {},
                        "school": {},
                    }
                ]
            }
        ]
    }
}
FIXTURE_BOXSCORE = {
    "teams": {
        "away": {
            "team": {"id": 147},
            "players": {
                "ID1": {
                    "person": {"id": 1, "fullName": "Player One"},
                    "position": {"code": "1", "name": "Pitcher"},
                    "status": {"code": "A"},
                    "stats": {"batting": {"atBats": 1}, "pitching": {}, "fielding": {"putOuts": 1}},
                }
            },
        },
        "home": {"team": {"id": 110}, "players": {}},
    },
    "officials": [{"official": {"id": 900, "fullName": "Ump One"}, "officialType": "Home Plate"}],
}
FIXTURE_WIN_PROB = [
    {
        "atBatIndex": 0,
        "about": {"inning": 1, "halfInning": "top"},
        "homeTeamWinProbability": 50.0,
        "awayTeamWinProbability": 50.0,
        "homeTeamWinProbabilityAdded": 0.0,
    }
]

# ADR-020 reference/personnel/official-stats fixtures.
FIXTURE_SPORTS = {"sports": [{"id": 1, "code": "mlb", "name": "Major League Baseball"}]}
FIXTURE_LEAGUES = {"leagues": [{"id": 103, "name": "American League", "seasonDateInfo": {}}]}
FIXTURE_DIVISIONS = {"divisions": [{"id": 200, "name": "AL West", "league": {"id": 103}}]}
FIXTURE_SEASONS = {"seasons": [{"seasonId": "2024"}]}
FIXTURE_PLAYER_POOL = {"people": [{"id": 1, "fullName": "Player One", "currentTeam": {"id": 110}}]}
FIXTURE_FREE_AGENTS = {"freeAgents": [{"player": {"id": 1, "fullName": "Player One"}}]}
FIXTURE_COACHES = {"roster": [{"person": {"id": 2, "fullName": "Coach One"}, "job": "Manager"}]}
FIXTURE_ALUMNI = {"people": [{"id": 3, "fullName": "Alum One"}]}
FIXTURE_PERSONNEL = {"roster": [{"person": {"id": 4, "fullName": "Staffer One"}, "job": "GM"}]}
FIXTURE_AFFILIATES = {"teams": [{"id": 500, "name": "Farm Team", "league": {}, "sport": {}}]}
FIXTURE_ATTENDANCE = {"records": [{"year": "2024", "gamesTotal": 81}]}
FIXTURE_GAME_PACE = {"sports": [{"hitsPer9Inn": 16.0}]}
FIXTURE_STATS = {
    "stats": [
        {
            "splits": [
                {
                    "player": {"id": 1, "fullName": "Player One"},
                    "team": {"id": 110},
                    "stat": {"homeRuns": 30},
                }
            ]
        }
    ]
}
FIXTURE_TEAM_STATS = {
    "stats": [{"splits": [{"team": {"id": 110, "name": "Orioles"}, "stat": {"wins": 90}}]}]
}
FIXTURE_STAT_LEADERS = {
    "leagueLeaders": [
        {"leaders": [{"rank": 1, "value": "58", "person": {"id": 1, "fullName": "P"}}]}
    ]
}
FIXTURE_TEAM_LEADERS = {
    "teamLeaders": [{"leaders": [{"rank": 1, "value": "58", "person": {"id": 1, "fullName": "P"}}]}]
}
FIXTURE_AWARDS = {"awards": [{"id": "NLMVP", "name": "NL MVP"}]}


class _FixedDate(date):
    @classmethod
    def today(cls):
        return date(2026, 6, 1)


@pytest.fixture(autouse=True)
def _fixed_range(monkeypatch):
    monkeypatch.setattr(mlb_api, "date", _FixedDate)
    monkeypatch.setattr(mlb_api, "FIRST_SCHEDULE_YEAR", 2024)
    monkeypatch.setattr(mlb_api, "FIRST_STANDINGS_YEAR", 2024)
    monkeypatch.setattr(mlb_api, "FIRST_ROSTER_YEAR", 2024)
    monkeypatch.setattr(mlb_api, "FIRST_TRANSACTION_YEAR", 2024)
    monkeypatch.setattr(mlb_api, "FIRST_PLAYBYPLAY_YEAR", 2026)
    monkeypatch.setattr(mlb_api, "FIRST_DRAFT_YEAR", 2024)


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


def _fake_get(endpoint, params=None, **kwargs):
    params = params or {}
    if endpoint == "teams":
        return FIXTURE_TEAMS
    if endpoint == "team_roster":
        return FIXTURE_ROSTER
    if endpoint == "transactions":
        return FIXTURE_TRANSACTIONS
    if endpoint == "game_playByPlay":
        return FIXTURE_PLAYBYPLAY
    if endpoint == "game_boxscore":
        return FIXTURE_BOXSCORE
    if endpoint == "game_winProbability":
        return FIXTURE_WIN_PROB
    if endpoint == "game":
        return FINAL_GAME_FEED
    if endpoint == "venue":
        return FIXTURE_VENUE_IDS if params.get("venueIds") == "" else FIXTURE_VENUE_DETAIL
    if endpoint == "teams_history":
        return FIXTURE_TEAM_HISTORY
    if endpoint == "people":
        return FIXTURE_PEOPLE
    if endpoint == "draft":
        return FIXTURE_DRAFT
    if endpoint == "sports":
        return FIXTURE_SPORTS
    if endpoint == "league":
        return FIXTURE_LEAGUES
    if endpoint == "divisions":
        return FIXTURE_DIVISIONS
    if endpoint == "seasons":
        return FIXTURE_SEASONS
    if endpoint == "sports_players":
        return FIXTURE_PLAYER_POOL
    if endpoint == "people_freeAgents":
        return FIXTURE_FREE_AGENTS
    if endpoint == "team_coaches":
        return FIXTURE_COACHES
    if endpoint == "team_alumni":
        return FIXTURE_ALUMNI
    if endpoint == "team_personnel":
        return FIXTURE_PERSONNEL
    if endpoint == "teams_affiliates":
        return FIXTURE_AFFILIATES
    if endpoint == "attendance":
        return FIXTURE_ATTENDANCE
    if endpoint == "gamePace":
        return FIXTURE_GAME_PACE
    if endpoint == "stats":
        return FIXTURE_STATS
    if endpoint == "teams_stats":
        return FIXTURE_TEAM_STATS
    if endpoint == "stats_leaders":
        return FIXTURE_STAT_LEADERS
    if endpoint == "team_leaders":
        return FIXTURE_TEAM_LEADERS
    if endpoint == "awards":
        return FIXTURE_AWARDS
    raise AssertionError(f"unexpected endpoint: {endpoint}")


def _mocked_statsapi():
    return patch.multiple(
        mlb_api.statsapi,
        schedule=lambda **kwargs: FIXTURE_GAMES_BY_SEASON.get(kwargs.get("season"), []),
        standings_data=lambda **kwargs: FIXTURE_STANDINGS_BY_SEASON.get(kwargs.get("season"), {}),
        get=_fake_get,
    )


def test_bootstrap_loads_full_history_across_multiple_seasons(db_conn):
    with _mocked_statsapi():
        counts = mlb_api.bootstrap()

    assert counts["raw.mlb_schedule"] == 6
    assert counts["raw.mlb_standing"] == 3
    assert counts["raw.mlb_roster"] == 3  # 1 player x 3 seasons (2024-2026)
    assert counts["raw.mlb_transaction"] == 3  # 1 transaction x 3 seasons
    assert (
        counts["raw.mlb_draft"] == 3
    )  # 1 pick x 3 seasons (2024-2026, FIRST_DRAFT_YEAR monkeypatched)
    assert counts["raw.mlb_playbyplay"] == 3  # 1 play x 3 completed 2026 games (all "Final")
    assert counts["raw.mlb_boxscore_batting"] == 3  # 1 batting-stat player x 3 games
    assert counts["raw.mlb_boxscore_fielding"] == 3
    assert counts["raw.mlb_umpire"] == 3  # 1 umpire x 3 games, 2026 game-detail only
    # win_prob covers all 6 games across all 3 seasons (2024/2025 via the
    # win-prob-only range, 2026 via full game-detail) — unlike playbyplay/
    # boxscore/umpire, which stay 2026-only (see FIRST_WIN_PROB_YEAR).
    assert counts["raw.mlb_win_prob"] == 6
    assert counts["raw.mlb_venue"] == 1
    assert counts["raw.mlb_team_history"] == 1
    assert counts["raw.mlb_person"] == 1
    # ADR-020 reference/personnel/official-stats data — season-scoped ones
    # (player_pool/free_agent/coach/alumni/game_pace/player_stat/team_stat/
    # stat_leader/team_leader) load once per season, same as schedule; the
    # whole-catalog/per-team-current ones (sport/league/division/season/
    # personnel/affiliate/attendance/award) load once, after the loop.
    assert counts["raw.mlb_player_pool"] == 3
    assert counts["raw.mlb_free_agent"] == 3
    assert counts["raw.mlb_coach"] == 3
    assert counts["raw.mlb_alumni"] == 6  # 1 team x 2 groups x 3 seasons
    assert counts["raw.mlb_game_pace"] == 3
    assert counts["raw.mlb_player_stat"] == 6  # 1 player x 2 groups x 3 seasons
    assert counts["raw.mlb_team_stat"] == 6
    # 10 LEADER_CATEGORIES x 1 leader row x 3 seasons.
    assert counts["raw.mlb_stat_leader"] == 30
    assert counts["raw.mlb_team_leader"] == 30
    assert counts["raw.mlb_sport"] == 1
    assert counts["raw.mlb_league"] == 1
    assert counts["raw.mlb_division"] == 1
    assert counts["raw.mlb_season"] == 1
    assert counts["raw.mlb_personnel"] == 1
    assert counts["raw.mlb_affiliate"] == 1
    assert counts["raw.mlb_attendance"] == 1
    assert counts["raw.mlb_award"] == 1

    with db_conn.cursor() as cur:
        cur.execute("SELECT _season, count(*) FROM raw.mlb_schedule GROUP BY _season ORDER BY 1")
        assert cur.fetchall() == [("2024", 2), ("2025", 1), ("2026", 3)]
        cur.execute("SELECT _season, w FROM raw.mlb_standing ORDER BY _season")
        assert cur.fetchall() == [("2024", "1"), ("2025", "2"), ("2026", "3")]
        cur.execute("SELECT DISTINCT game_pk FROM raw.mlb_playbyplay ORDER BY 1")
        assert cur.fetchall() == [("2004",), ("2005",), ("2006",)]
        cur.execute("SELECT _season, count(*) FROM raw.mlb_win_prob GROUP BY _season ORDER BY 1")
        assert cur.fetchall() == [("2024", 2), ("2025", 1), ("2026", 3)]
        cur.execute("SELECT venue_id, city FROM raw.mlb_venue")
        assert cur.fetchall() == [("100", "Springfield")]
        cur.execute("SELECT person_id, full_name FROM raw.mlb_person")
        assert cur.fetchall() == [("1", "Player One")]


def test_bootstrap_is_idempotent_for_venue_team_history_person(db_conn):
    with _mocked_statsapi():
        mlb_api.bootstrap()
        mlb_api.bootstrap()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.mlb_venue")
        assert cur.fetchone() == (1,)
        cur.execute("SELECT count(*) FROM raw.mlb_team_history")
        assert cur.fetchone() == (1,)
        cur.execute("SELECT count(*) FROM raw.mlb_person")
        assert cur.fetchone() == (1,)


def test_bootstrap_boxscore_and_umpires_replace_not_duplicate_per_game(db_conn):
    with _mocked_statsapi():
        mlb_api.bootstrap()
        mlb_api.bootstrap()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.mlb_boxscore_batting WHERE game_pk = '2004'")
        assert cur.fetchone() == (1,)
        cur.execute("SELECT count(*) FROM raw.mlb_umpire WHERE game_pk = '2004'")
        assert cur.fetchone() == (1,)
        cur.execute("SELECT count(*) FROM raw.mlb_win_prob WHERE game_pk = '2004'")
        assert cur.fetchone() == (1,)


def test_bootstrap_skips_a_failing_season_and_continues(db_conn):
    def flaky_schedule(**kwargs):
        if kwargs.get("season") == 2025:
            raise RuntimeError("simulated transient API failure")
        return FIXTURE_GAMES_BY_SEASON.get(kwargs.get("season"), [])

    with (
        patch.object(mlb_api.statsapi, "schedule", side_effect=flaky_schedule),
        patch.object(mlb_api.statsapi, "standings_data", side_effect=lambda **k: {}),
        patch.object(mlb_api.statsapi, "get", side_effect=_fake_get),
    ):
        counts = mlb_api.bootstrap()

    # 2025's 1 game is missing, but 2024's 2 and 2026's 3 still landed.
    assert counts["raw.mlb_schedule"] == 5
    with db_conn.cursor() as cur:
        cur.execute("SELECT DISTINCT _season FROM raw.mlb_schedule ORDER BY 1")
        assert cur.fetchall() == [("2024",), ("2026",)]


def test_bootstrap_skips_a_failing_game_playbyplay_and_continues(db_conn):
    def flaky_get(endpoint, params=None, **kwargs):
        params = params or {}
        if endpoint == "game_playByPlay" and params.get("gamePk") == 2005:
            raise RuntimeError("simulated transient API failure")
        return _fake_get(endpoint, params, **kwargs)

    with (
        patch.object(
            mlb_api.statsapi,
            "schedule",
            side_effect=lambda **kwargs: FIXTURE_GAMES_BY_SEASON.get(kwargs.get("season"), []),
        ),
        patch.object(mlb_api.statsapi, "standings_data", side_effect=lambda **k: {}),
        patch.object(mlb_api.statsapi, "get", side_effect=flaky_get),
    ):
        counts = mlb_api.bootstrap()

    # game 2005's play failed, but 2004's and 2006's still landed.
    assert counts["raw.mlb_playbyplay"] == 2
    with db_conn.cursor() as cur:
        cur.execute("SELECT DISTINCT game_pk FROM raw.mlb_playbyplay ORDER BY 1")
        assert cur.fetchall() == [("2004",), ("2006",)]


def test_update_reloads_current_season_only_and_replaces_not_duplicates(db_conn):
    with _mocked_statsapi():
        mlb_api.bootstrap()
        mlb_api.update()

    with db_conn.cursor() as cur:
        cur.execute("SELECT _season, count(*) FROM raw.mlb_schedule GROUP BY _season ORDER BY 1")
        # Only 2026 (the "current" season under _FixedDate) gets touched again.
        assert cur.fetchall() == [("2024", 2), ("2025", 1), ("2026", 3)]
        cur.execute("SELECT _season, count(*) FROM raw.mlb_roster GROUP BY _season ORDER BY 1")
        assert cur.fetchall() == [("2024", 1), ("2025", 1), ("2026", 1)]


def test_update_refreshes_playbyplay_for_todays_started_games_only(db_conn):
    schedule_today = [
        _game(5001, 2026, status="Final"),
        _game(5002, 2026, status="Scheduled"),  # hasn't started — no plays yet
    ]

    def schedule_dispatch(**kwargs):
        if "date" in kwargs:
            return schedule_today
        return FIXTURE_GAMES_BY_SEASON.get(kwargs.get("season"), [])

    with (
        patch.object(mlb_api.statsapi, "schedule", side_effect=schedule_dispatch),
        patch.object(mlb_api.statsapi, "standings_data", side_effect=lambda **k: {}),
        patch.object(mlb_api.statsapi, "get", side_effect=_fake_get),
    ):
        counts = mlb_api.update()

    assert counts["raw.mlb_playbyplay"] > 0
    with db_conn.cursor() as cur:
        cur.execute("SELECT DISTINCT game_pk FROM raw.mlb_playbyplay ORDER BY 1")
        assert cur.fetchall() == [("5001",)]  # 5002 never started, correctly skipped


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


def test_update_includes_all_counts(db_conn):
    with _mocked_statsapi():
        counts = mlb_api.update()

    assert set(counts) == {
        "raw.mlb_schedule",
        "raw.mlb_standing",
        "raw.mlb_roster",
        "raw.mlb_transaction",
        "raw.mlb_draft",
        "raw.mlb_playbyplay",
        "raw.mlb_boxscore_batting",
        "raw.mlb_boxscore_pitching",
        "raw.mlb_boxscore_fielding",
        "raw.mlb_umpire",
        "raw.mlb_win_prob",
        "raw.mlb_live_game",
    }
    assert counts["raw.mlb_schedule"] == 3
    assert counts["raw.mlb_standing"] == 1
    assert counts["raw.mlb_live_game"] == 0  # FINAL_GAME_FEED — nothing live today
    # update()'s schedule(date=...) call doesn't match FIXTURE_GAMES_BY_SEASON
    # (keyed by season, not date) — no started games today under this fixture.
    assert counts["raw.mlb_playbyplay"] == 0


def test_update_does_not_touch_reference_personnel_stat_data(db_conn):
    # ADR-020: update() (called every 5 minutes by cron) deliberately never
    # refreshes the reference/personnel/official-stats data — only
    # bootstrap() does. A regression here would mean cron starts making
    # ~30 teams' worth of extra API calls every 5 minutes for data that
    # never changes that fast.
    with _mocked_statsapi():
        mlb_api.bootstrap()
        mlb_api.update()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.mlb_coach")
        bootstrap_only_count = cur.fetchone()[0]
    assert bootstrap_only_count > 0
    # A second update() must not add or duplicate rows here.
    with _mocked_statsapi():
        mlb_api.update()
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.mlb_coach")
        assert cur.fetchone()[0] == bootstrap_only_count


def test_bootstrap_is_idempotent_for_reference_personnel_stat_data(db_conn):
    with _mocked_statsapi():
        mlb_api.bootstrap()
        mlb_api.bootstrap()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.mlb_sport")
        assert cur.fetchone() == (1,)
        cur.execute("SELECT count(*) FROM raw.mlb_attendance")
        assert cur.fetchone() == (1,)
        cur.execute("SELECT _season, count(*) FROM raw.mlb_player_pool GROUP BY _season ORDER BY 1")
        assert cur.fetchall() == [("2024", 1), ("2025", 1), ("2026", 1)]


def test_health_check_reports_healthy_with_zero_live_and_playbyplay_rows(db_conn):
    # check_table_exists (not check_table_has_rows) backs raw.mlb_live_game
    # and raw.mlb_playbyplay specifically because 0 rows there is a normal,
    # healthy state — nothing live/started right now isn't "never bootstrapped."
    with _mocked_statsapi():
        mlb_api.bootstrap()
        mlb_api.update()
    db_conn.commit()

    checks = mlb_api.health_check()

    live_check = next(c for c in checks if c.name == "raw.mlb_live_game")
    assert live_check.ok
    roster_check = next(c for c in checks if c.name == "raw.mlb_roster")
    assert roster_check.ok
    tx_check = next(c for c in checks if c.name == "raw.mlb_transaction")
    assert tx_check.ok


def test_win_prob_only_range_is_idempotent_across_bootstrap_reruns(db_conn):
    # FIRST_WIN_PROB_YEAR (1950, not monkeypatched here since 2024/2025 both
    # already fall under it in this fixture's 2024-2026 window) covers
    # 2024/2025 for win_prob only — a second bootstrap() run must not
    # re-fetch (and re-insert) those already-loaded seasons.
    with _mocked_statsapi():
        mlb_api.bootstrap()
        mlb_api.bootstrap()

    with db_conn.cursor() as cur:
        cur.execute("SELECT _season, count(*) FROM raw.mlb_win_prob GROUP BY _season ORDER BY 1")
        assert cur.fetchall() == [("2024", 2), ("2025", 1), ("2026", 3)]


def test_win_prob_only_range_skips_playbyplay_boxscore_umpire(db_conn):
    # The whole point of splitting win_prob out from game-detail: 2024/2025
    # must NOT get playbyplay/boxscore/umpire rows, only win_prob.
    with _mocked_statsapi():
        mlb_api.bootstrap()

    with db_conn.cursor() as cur:
        cur.execute("SELECT DISTINCT _season FROM raw.mlb_playbyplay")
        assert cur.fetchall() == [("2026",)]
        cur.execute(
            "SELECT count(*) FROM raw.mlb_boxscore_batting "
            "WHERE game_pk IN ('2001', '2002', '2003')"
        )
        assert cur.fetchone() == (0,)


def test_win_prob_for_season_skips_whole_season_on_schedule_fetch_failure(db_conn):
    # Regression: a season's own statsapi.schedule() call failing must not
    # crash the entire multi-decade bootstrap loop — caught and skipped,
    # same as every other per-season failure mode in this connector.
    def flaky_schedule(**kwargs):
        if kwargs.get("season") == 2024:
            raise RuntimeError("simulated transient API failure")
        return FIXTURE_GAMES_BY_SEASON.get(kwargs.get("season"), [])

    with (
        patch.object(mlb_api.statsapi, "schedule", side_effect=flaky_schedule),
        patch.object(mlb_api.statsapi, "standings_data", side_effect=lambda **k: {}),
        patch.object(mlb_api.statsapi, "get", side_effect=_fake_get),
    ):
        counts = mlb_api.bootstrap()

    # 2024's win_prob failed (schedule fetch itself raised), but 2025/2026 landed.
    assert counts["raw.mlb_win_prob"] == 4  # 1 (2025) + 3 (2026)
    with db_conn.cursor() as cur:
        cur.execute("SELECT DISTINCT _season FROM raw.mlb_win_prob ORDER BY 1")
        assert cur.fetchall() == [("2025",), ("2026",)]


def test_first_win_prob_year_boundary_matches_real_confirmed_coverage():
    # Confirmed via direct testing against the real API: gamePk-based
    # game_winProbability/game_playByPlay/game_boxscore return real,
    # populated data for a 1950 game, but 404/empty for 1949 and every
    # year checked back to 1901.
    assert mlb_api.FIRST_WIN_PROB_YEAR == 1950
