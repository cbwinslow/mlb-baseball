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


def test_roster_df_pulls_teams_for_the_season_then_flattens_each_players_entry():
    teams = {"teams": [{"id": 110}, {"id": 147}]}
    rosters = {
        110: {
            "roster": [
                {
                    "person": {"id": 1, "fullName": "Player One"},
                    "jerseyNumber": "10",
                    "position": {"code": "1", "name": "Pitcher", "type": "Pitcher"},
                    "status": {"code": "A", "description": "Active"},
                }
            ]
        },
        147: {"roster": []},
    }

    def fake_get(endpoint, params, **kwargs):
        if endpoint == "teams":
            return teams
        return rosters[params["teamId"]]

    with patch.object(mlb_api.statsapi, "get", side_effect=fake_get):
        df = mlb_api._roster_df(2024)

    assert len(df) == 1
    row = df.iloc[0]
    assert row["team_id"] == 110
    assert row["person_id"] == 1
    assert row["person_name"] == "Player One"
    assert row["position_name"] == "Pitcher"
    assert row["status_code"] == "A"
    assert row["_season"] == "2024"


def test_season_team_ids_returns_empty_list_not_crash_for_season_with_no_teams():
    with patch.object(mlb_api.statsapi, "get", return_value={"teams": []}):
        assert mlb_api._season_team_ids(1875) == []


def test_transactions_df_flattens_person_and_team_objects():
    payload = {
        "transactions": [
            {
                "id": 1,
                "person": {"id": 5, "fullName": "Some Player"},
                "fromTeam": {"id": 110, "name": "Orioles"},
                "toTeam": {"id": 147, "name": "Yankees"},
                "date": "2024-07-01",
                "typeCode": "TR",
                "typeDesc": "Trade",
                "description": "Traded.",
            }
        ]
    }
    with patch.object(mlb_api.statsapi, "get", return_value=payload) as mock_get:
        df = mlb_api._transactions_df(2024)

    # force=True since statsapi's own required-param validation is buggy for
    # startDate/endDate (see module docstring) — confirm we're passing it.
    assert mock_get.call_args.kwargs.get("force") is True
    assert len(df) == 1
    row = df.iloc[0]
    assert row["person_id"] == 5
    assert row["from_team_name"] == "Orioles"
    assert row["to_team_name"] == "Yankees"
    assert row["type_code"] == "TR"
    assert row["_season"] == "2024"


def test_transactions_df_handles_missing_from_team_without_crashing():
    # Real data: many transactions (free agent signings, waiver claims) have
    # no fromTeam at all — must degrade to None, not KeyError.
    payload = {
        "transactions": [{"id": 1, "person": {"id": 5}, "toTeam": {"id": 147, "name": "Yankees"}}]
    }
    with patch.object(mlb_api.statsapi, "get", return_value=payload):
        df = mlb_api._transactions_df(2024)

    assert df.iloc[0]["from_team_id"] is None
    assert df.iloc[0]["from_team_name"] is None


PLAYBYPLAY_FEED = {
    "allPlays": [
        {
            "atBatIndex": 0,
            "about": {"inning": 1, "halfInning": "top"},
            "count": {"balls": 1, "strikes": 2, "outs": 1},
            "matchup": {
                "batter": {"id": 660271, "fullName": "Shohei Ohtani"},
                "batSide": {"code": "L"},
                "pitcher": {"id": 684007, "fullName": "Shota Imanaga"},
                "pitchHand": {"code": "L"},
            },
            "result": {
                "event": "Groundout",
                "eventType": "field_out",
                "description": "Ohtani grounds out.",
                "rbi": 0,
                "awayScore": 0,
                "homeScore": 0,
            },
        }
    ]
}


def test_playbyplay_df_flattens_one_row_per_plate_appearance():
    with patch.object(mlb_api.statsapi, "get", return_value=PLAYBYPLAY_FEED):
        df = mlb_api._playbyplay_df(778563)

    assert len(df) == 1
    row = df.iloc[0]
    assert row["game_pk"] == 778563
    assert row["batter_name"] == "Shohei Ohtani"
    assert row["pitcher_name"] == "Shota Imanaga"
    assert row["event"] == "Groundout"
    assert row["inning"] == 1
    assert row["half_inning"] == "top"


def test_started_game_ids_excludes_not_yet_played_statuses():
    games = [
        {"game_id": 1, "status": "Final"},
        {"game_id": 2, "status": "Scheduled"},
        {"game_id": 3, "status": "In Progress"},
        {"game_id": 4, "status": "Postponed"},
        {"game_id": 5, "status": "Completed Early"},
    ]
    assert mlb_api._started_game_ids(games) == [1, 3, 5]


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
