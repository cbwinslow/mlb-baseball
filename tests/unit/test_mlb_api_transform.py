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
