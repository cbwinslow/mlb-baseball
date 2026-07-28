"""Pure transform logic — statsapi itself is mocked, no DB, no real HTTP."""

from unittest.mock import patch

from mlb_baseball.connectors import mlb_api_extra as extra


def test_load_leagues_flattens_season_date_info():
    payload = {
        "leagues": [
            {
                "id": 103,
                "name": "American League",
                "abbreviation": "AL",
                "seasonDateInfo": {"seasonId": "2026", "seasonStartDate": "2026-02-20"},
            }
        ]
    }
    with patch.object(extra.statsapi, "get", return_value=payload):
        with patch.object(extra, "load_dataframe") as mock_load:
            extra._load_leagues(object())
    df = mock_load.call_args.args[2]
    assert df.iloc[0]["name"] == "American League"
    assert df.iloc[0]["season_seasonStartDate"] == "2026-02-20"


def test_load_divisions_flattens_league_id():
    payload = {
        "divisions": [
            {"id": 200, "name": "AL West", "league": {"id": 103}, "active": True},
        ]
    }
    with patch.object(extra.statsapi, "get", return_value=payload):
        with patch.object(extra, "load_dataframe") as mock_load:
            extra._load_divisions(object())
    df = mock_load.call_args.args[2]
    assert df.iloc[0]["league_id"] == 103


def test_load_player_pool_flattens_current_team():
    payload = {
        "people": [
            {
                "id": 1,
                "fullName": "Player One",
                "birthDate": "2000-01-01",
                "currentTeam": {"id": 110, "name": "Orioles"},
                "active": True,
            }
        ]
    }
    with patch.object(extra.statsapi, "get", return_value=payload):
        with patch.object(extra, "load_dataframe") as mock_load:
            extra._load_player_pool(object(), 2024)
    df = mock_load.call_args.args[2]
    assert df.iloc[0]["current_team_name"] == "Orioles"
    assert df.iloc[0]["_season"] == "2024"


def test_load_player_pool_returns_zero_without_touching_db_when_empty():
    with patch.object(extra.statsapi, "get", return_value={"people": []}):
        with patch.object(extra, "load_dataframe") as mock_load:
            count = extra._load_player_pool(object(), 2024)
    assert count == 0
    mock_load.assert_not_called()


def test_load_free_agents_calls_with_force_true_and_flattens_teams():
    payload = {
        "freeAgents": [
            {
                "player": {"id": 5, "fullName": "Some Player"},
                "originalTeam": {"id": 110, "name": "Orioles"},
                "newTeam": {"id": 147, "name": "Yankees"},
                "notes": "Signed.",
                "rank": 3,
            }
        ]
    }
    with patch.object(extra.statsapi, "get", return_value=payload) as mock_get:
        with patch.object(extra, "load_dataframe") as mock_load:
            extra._load_free_agents(object(), 2024)
    assert mock_get.call_args.kwargs.get("force") is True
    df = mock_load.call_args.args[2]
    assert df.iloc[0]["original_team_name"] == "Orioles"
    assert df.iloc[0]["new_team_name"] == "Yankees"


def test_load_attendance_stamps_team_id_on_every_record():
    payload = {
        "records": [{"year": "1903", "gamesTotal": 136}, {"year": "1904", "gamesTotal": 140}]
    }
    with patch.object(extra.statsapi, "get", return_value=payload):
        with patch.object(extra, "_season_team_ids", return_value=[147]):
            with patch.object(extra, "load_dataframe") as mock_load:
                extra._load_attendance(object())
    df = mock_load.call_args.args[2]
    assert set(df["team_id"]) == {147}
    assert len(df) == 2


def test_load_alumni_pulls_both_groups_per_team():
    calls = []

    def fake_get(endpoint, params, **kwargs):
        calls.append(params.get("group"))
        return {"people": [{"id": 1, "fullName": "Player One"}]}

    with patch.object(extra.statsapi, "get", side_effect=fake_get):
        with patch.object(extra, "_season_team_ids", return_value=[147]):
            with patch.object(extra, "load_dataframe", return_value=1):
                total = extra._load_alumni(object(), 2024)
    assert calls == ["hitting", "pitching"]
    assert total == 2
