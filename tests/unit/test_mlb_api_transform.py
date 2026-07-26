"""Pure transform logic — statsapi itself is mocked, no DB, no real HTTP."""

from unittest.mock import patch

from mlb_baseball.connectors import mlb_api


def test_schedule_df_serializes_national_broadcasts_as_json_not_python_repr():
    games = [
        {"game_id": 1, "national_broadcasts": ["FOX", "MLBN"]},
        {"game_id": 2, "national_broadcasts": []},
    ]
    with patch.object(mlb_api.statsapi, "schedule", return_value=games):
        df = mlb_api._schedule_df(2026)

    assert df.loc[df["game_id"] == 1, "national_broadcasts"].iloc[0] == '["FOX", "MLBN"]'
    assert df.loc[df["game_id"] == 2, "national_broadcasts"].iloc[0] == "[]"
    assert (df["_season"] == "2026").all()


def test_schedule_df_coalesces_miscased_losing_team_key():
    # Real statsapi quirk: tied Spring Training/Exhibition games come back
    # with "losing_Team" (capital T) instead of "losing_team" — confirmed
    # against real 2026 data (22 games, all ties). Uncoalesced, this would
    # collide with "losing_team" once column names are lowercased and crash
    # CREATE TABLE with a DuplicateColumn error.
    games = [{"game_id": 1, "winning_team": "Tie", "losing_Team": "Tie"}]
    with patch.object(mlb_api.statsapi, "schedule", return_value=games):
        df = mlb_api._schedule_df(2026)

    assert "losing_Team" not in df.columns
    assert df.loc[0, "losing_team"] == "Tie"


def test_standings_df_flattens_division_id_and_name_onto_each_team_row():
    standings = {
        201: {
            "div_name": "American League East",
            "teams": [{"name": "Baltimore Orioles", "team_id": 110, "w": 1, "l": 0}],
        },
        203: {
            "div_name": "American League Central",
            "teams": [{"name": "Cleveland Guardians", "team_id": 114, "w": 0, "l": 1}],
        },
    }
    with patch.object(mlb_api.statsapi, "standings_data", return_value=standings):
        df = mlb_api._standings_df(2026)

    assert len(df) == 2
    row = df[df["name"] == "Baltimore Orioles"].iloc[0]
    assert row["division_id"] == 201
    assert row["div_name"] == "American League East"
    assert row["_season"] == "2026"


def test_schedule_year_boundary_matches_real_confirmed_coverage():
    # Confirmed via direct testing against the real API before writing this
    # (see mlb_api.py's module docstring): 1900 and earlier return 0 games,
    # 1901 is the first real season. A regression here (e.g. someone "fixing"
    # this back to 1871 without re-checking) would make bootstrap() spend a
    # long time on decades of empty API calls.
    assert mlb_api.FIRST_SCHEDULE_YEAR == 1901


def test_standings_year_boundary_matches_real_confirmed_coverage():
    # Confirmed via direct testing: statsapi's standings_data() raises
    # KeyError('division') for any season before 1969 (divisions didn't
    # exist yet). 1969 is the first season it can represent.
    assert mlb_api.FIRST_STANDINGS_YEAR == 1969


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


def test_live_snapshot_returns_none_when_game_is_not_live():
    for state in ["Preview", "Final"]:
        feed = {"gameData": {"status": {"abstractGameState": state}}, "liveData": {}}
        with patch.object(mlb_api.statsapi, "get", return_value=feed):
            assert mlb_api._live_snapshot(123) is None


def test_live_snapshot_flattens_linescore_fields_when_live():
    with patch.object(mlb_api.statsapi, "get", return_value=LIVE_GAME_FEED):
        snapshot = mlb_api._live_snapshot(123)

    assert snapshot["game_pk"] == 123
    assert snapshot["current_inning"] == 5
    assert snapshot["inning_state"] == "Top"
    assert snapshot["away_runs"] == 2
    assert snapshot["home_errors"] == 1
    assert snapshot["balls"] == 1
    assert snapshot["strikes"] == 2
    assert snapshot["outs"] == 1
    assert snapshot["batter_id"] == 111
    assert snapshot["batter_name"] == "Batter One"
    assert snapshot["pitcher_id"] == 222
    assert snapshot["pitcher_name"] == "Pitcher One"


def test_live_snapshot_handles_missing_offense_defense_without_crashing():
    # A game can be "Live" between half-innings/pitching changes where
    # offense/defense aren't populated yet — must degrade to None, not KeyError.
    feed = {
        "gameData": {
            "status": {"abstractGameState": "Live"},
            "datetime": {"officialDate": "2026-06-01"},
            "teams": {"away": {"name": "Yankees"}, "home": {"name": "Orioles"}},
        },
        "liveData": {"linescore": {"currentInning": 1}},
    }
    with patch.object(mlb_api.statsapi, "get", return_value=feed):
        snapshot = mlb_api._live_snapshot(123)

    assert snapshot["batter_id"] is None
    assert snapshot["pitcher_name"] is None
