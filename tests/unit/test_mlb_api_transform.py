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


def test_camel_to_snake_matches_real_mlb_api_field_names():
    assert mlb_api._camel_to_snake("atBats") == "at_bats"
    assert mlb_api._camel_to_snake("atBatsPerHomeRun") == "at_bats_per_home_run"
    assert mlb_api._camel_to_snake("era") == "era"
    assert mlb_api._camel_to_snake("homeTeamWinProbability") == "home_team_win_probability"


def test_venue_df_flattens_nested_location_fieldinfo_timezone():
    payload = {
        "venues": [
            {
                "id": 2857,
                "name": "Test Park",
                "active": True,
                "location": {
                    "address1": "1 Main St",
                    "city": "Springfield",
                    "state": "IL",
                    "postalCode": "62701",
                    "country": "USA",
                    "defaultCoordinates": {"latitude": 1.1, "longitude": -2.2},
                },
                "timeZone": {"id": "America/Chicago"},
                "fieldInfo": {
                    "capacity": 5000,
                    "turfType": "Grass",
                    "roofType": "Open",
                    "leftLine": 330,
                    "center": 400,
                    "rightLine": 330,
                },
            }
        ]
    }
    with patch.object(mlb_api.statsapi, "get", return_value=payload):
        df = mlb_api._venue_df()

    assert len(df) == 1
    row = df.iloc[0]
    assert row["venue_id"] == 2857
    assert row["city"] == "Springfield"
    assert row["latitude"] == 1.1
    assert row["capacity"] == 5000
    assert row["turf_type"] == "Grass"


def test_venue_df_batches_ids_across_multiple_calls():
    # VENUE_BATCH_SIZE is 100 — more ids than that must trigger a second call,
    # not silently truncate to the first batch.
    ids = list(range(1, 251))

    def fake_get(endpoint, params, **kwargs):
        if params.get("venueIds") == "":
            return {"venues": [{"id": i} for i in ids]}
        requested = [int(v) for v in params["venueIds"].split(",")]
        return {"venues": [{"id": v, "name": f"Park {v}"} for v in requested]}

    with patch.object(mlb_api.statsapi, "get", side_effect=fake_get) as mock_get:
        df = mlb_api._venue_df()

    assert len(df) == 250
    # 1 call for the id list + 3 batches of 100/100/50
    assert mock_get.call_count == 4


def test_team_history_df_flattens_venue_and_league():
    payload = {
        "teams": [
            {
                "id": 147,
                "season": 1903,
                "name": "New York Highlanders",
                "teamCode": "nya",
                "abbreviation": "NYY",
                "locationName": "Manhattan",
                "franchiseName": "New York",
                "clubName": "Highlanders",
                "firstYearOfPlay": "1903",
                "venue": {"id": 100, "name": "Hilltop Park"},
                "league": {"name": "American League"},
                "active": True,
            }
        ]
    }
    with patch.object(mlb_api.statsapi, "get", return_value=payload):
        df = mlb_api._team_history_df(147)

    assert len(df) == 1
    row = df.iloc[0]
    assert row["season"] == 1903
    assert row["venue_name"] == "Hilltop Park"
    assert row["league_name"] == "American League"


def test_person_df_batches_and_flattens_bio_fields():
    ids = list(range(1, 5))

    def fake_get(endpoint, params, **kwargs):
        requested = [int(p) for p in params["personIds"].split(",")]
        return {
            "people": [
                {
                    "id": p,
                    "fullName": f"Player {p}",
                    "birthDate": "2000-01-01",
                    "primaryPosition": {"code": "1", "name": "Pitcher"},
                    "batSide": {"code": "R"},
                    "pitchHand": {"code": "L"},
                }
                for p in requested
            ]
        }

    with patch.object(mlb_api.statsapi, "get", side_effect=fake_get):
        df = mlb_api._person_df(ids)

    assert len(df) == 4
    row = df[df["person_id"] == 2].iloc[0]
    assert row["full_name"] == "Player 2"
    assert row["primary_position_name"] == "Pitcher"
    assert row["bat_side"] == "R"
    assert row["pitch_hand"] == "L"


def test_draft_df_flattens_nested_person_team_school_home():
    payload = {
        "drafts": {
            "rounds": [
                {
                    "picks": [
                        {
                            "pickRound": "1",
                            "pickNumber": 1,
                            "roundPickNumber": 1,
                            "pickValue": "9721000",
                            "signingBonus": "9200000",
                            "person": {"id": 694973, "fullName": "Paul Skenes"},
                            "team": {"id": 134, "name": "Pittsburgh Pirates"},
                            "home": {"city": "Lake Forest", "state": "CA", "country": "USA"},
                            "school": {"name": "LSU", "schoolClass": "4YR JR"},
                            "scoutingReport": "https://example.com",
                            "blurb": "A great prospect.",
                        }
                    ]
                }
            ]
        }
    }
    with patch.object(mlb_api.statsapi, "get", return_value=payload):
        df = mlb_api._draft_df(2023)

    assert len(df) == 1
    row = df.iloc[0]
    assert row["draft_year"] == 2023
    assert row["person_name"] == "Paul Skenes"
    assert row["team_name"] == "Pittsburgh Pirates"
    assert row["school_name"] == "LSU"
    assert row["home_city"] == "Lake Forest"


def test_draft_year_boundary_matches_real_confirmed_coverage():
    # Confirmed via direct testing: 1964 (statsapi.get('draft', {'year': 1964}))
    # returns 0 rounds; 1965 (MLB's first amateur draft) returns 72/824 picks.
    assert mlb_api.FIRST_DRAFT_YEAR == 1965


BOXSCORE_FEED = {
    "teams": {
        "away": {
            "team": {"id": 119},
            "players": {
                "ID1": {
                    "person": {"id": 1, "fullName": "Batter One"},
                    "position": {"code": "2", "name": "Catcher"},
                    "status": {"code": "A"},
                    "jerseyNumber": "16",
                    "battingOrder": "100",
                    "stats": {
                        "batting": {"atBats": 4, "hits": 1},
                        "pitching": {},
                        "fielding": {"putOuts": 6, "errors": 0},
                    },
                },
                "ID2": {
                    "person": {"id": 2, "fullName": "Pitcher One"},
                    "position": {"code": "1", "name": "Pitcher"},
                    "status": {"code": "A"},
                    "jerseyNumber": "41",
                    "battingOrder": None,
                    "stats": {
                        "batting": {},
                        "pitching": {"inningsPitched": "5.0", "strikeOuts": 3},
                        "fielding": {"putOuts": 1, "errors": 0},
                    },
                },
            },
        },
        "home": {"team": {"id": 147}, "players": {}},
    },
    "officials": [
        {"official": {"id": 500, "fullName": "Ump One"}, "officialType": "Home Plate"},
    ],
}


def test_boxscore_rows_splits_into_batting_pitching_fielding_by_nonempty_stats():
    batting, pitching, fielding = mlb_api._boxscore_rows(BOXSCORE_FEED, game_pk=777)

    assert len(batting) == 1
    assert batting[0]["person_name"] == "Batter One"
    assert batting[0]["at_bats"] == 4
    assert batting[0]["team_id"] == 119

    assert len(pitching) == 1
    assert pitching[0]["person_name"] == "Pitcher One"
    assert pitching[0]["innings_pitched"] == "5.0"
    assert pitching[0]["strike_outs"] == 3

    # Both players recorded a fielding line.
    assert len(fielding) == 2


def test_officials_rows_flattens_umpire_assignments():
    rows = mlb_api._officials_rows(BOXSCORE_FEED, game_pk=777)
    assert rows == [
        {
            "game_pk": 777,
            "person_id": 500,
            "person_name": "Ump One",
            "official_type": "Home Plate",
        }
    ]


def test_win_prob_rows_flattens_per_at_bat_probabilities():
    data = [
        {
            "atBatIndex": 0,
            "about": {"inning": 1, "halfInning": "top"},
            "homeTeamWinProbability": 46.4,
            "awayTeamWinProbability": 53.6,
            "homeTeamWinProbabilityAdded": -3.6,
        }
    ]
    rows = mlb_api._win_prob_rows(data, game_pk=777)
    assert rows == [
        {
            "game_pk": 777,
            "at_bat_index": 0,
            "inning": 1,
            "half_inning": "top",
            "home_win_probability": 46.4,
            "away_win_probability": 53.6,
            "home_win_probability_added": -3.6,
        }
    ]


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
    with patch.object(mlb_api.statsapi, "get", return_value=payload):
        with patch.object(mlb_api, "load_dataframe") as mock_load:
            mlb_api._load_leagues(object())
    df = mock_load.call_args.args[2]
    assert df.iloc[0]["name"] == "American League"
    assert df.iloc[0]["season_seasonStartDate"] == "2026-02-20"


def test_load_divisions_flattens_league_id():
    payload = {
        "divisions": [
            {"id": 200, "name": "AL West", "league": {"id": 103}, "active": True},
        ]
    }
    with patch.object(mlb_api.statsapi, "get", return_value=payload):
        with patch.object(mlb_api, "load_dataframe") as mock_load:
            mlb_api._load_divisions(object())
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
    with patch.object(mlb_api.statsapi, "get", return_value=payload):
        with patch.object(mlb_api, "load_dataframe") as mock_load:
            mlb_api._load_player_pool(object(), 2024)
    df = mock_load.call_args.args[2]
    assert df.iloc[0]["current_team_name"] == "Orioles"
    assert df.iloc[0]["_season"] == "2024"


def test_load_player_pool_returns_zero_without_touching_db_when_empty():
    with patch.object(mlb_api.statsapi, "get", return_value={"people": []}):
        with patch.object(mlb_api, "load_dataframe") as mock_load:
            count = mlb_api._load_player_pool(object(), 2024)
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
    with patch.object(mlb_api.statsapi, "get", return_value=payload) as mock_get:
        with patch.object(mlb_api, "load_dataframe") as mock_load:
            mlb_api._load_free_agents(object(), 2024)
    assert mock_get.call_args.kwargs.get("force") is True
    df = mock_load.call_args.args[2]
    assert df.iloc[0]["original_team_name"] == "Orioles"
    assert df.iloc[0]["new_team_name"] == "Yankees"


def test_load_attendance_stamps_team_id_on_every_record():
    payload = {
        "records": [{"year": "1903", "gamesTotal": 136}, {"year": "1904", "gamesTotal": 140}]
    }
    with patch.object(mlb_api.statsapi, "get", return_value=payload):
        with patch.object(mlb_api, "_season_team_ids", return_value=[147]):
            with patch.object(mlb_api, "load_dataframe") as mock_load:
                mlb_api._load_attendance(object())
    df = mock_load.call_args.args[2]
    assert set(df["team_id"]) == {147}
    assert len(df) == 2


def test_load_alumni_pulls_both_groups_per_team():
    calls = []

    def fake_get(endpoint, params, **kwargs):
        calls.append(params.get("group"))
        return {"people": [{"id": 1, "fullName": "Player One"}]}

    with patch.object(mlb_api.statsapi, "get", side_effect=fake_get):
        with patch.object(mlb_api, "_season_team_ids", return_value=[147]):
            with patch.object(mlb_api, "load_dataframe", return_value=1):
                total = mlb_api._load_alumni(object(), 2024)
    assert calls == ["hitting", "pitching"]
    # Both groups are collected before one season-scoped COPY.  That keeps a
    # rerun atomic across the two endpoint calls instead of replacing the
    # same scope twice.
    assert total == 1


def test_load_stats_flattens_and_snake_cases_camel_stat_fields():
    payload = {
        "stats": [
            {
                "splits": [
                    {
                        "player": {"id": 1, "fullName": "Player One"},
                        "team": {"id": 110},
                        "stat": {"homeRuns": 30, "atBatsPerHomeRun": "20.1"},
                    }
                ]
            }
        ]
    }
    with patch.object(mlb_api.statsapi, "get", return_value=payload):
        with patch.object(mlb_api, "load_dataframe") as mock_load:
            mlb_api._load_stats(object(), 2024)
    # The two endpoint responses are combined into one season-scoped COPY.
    # This makes the replacement idempotent and prevents the second group
    # from deleting rows written by the first group.
    assert mock_load.call_count == 1
    first_df = mock_load.call_args.args[2]
    assert first_df.iloc[0]["home_runs"] == 30
    assert first_df.iloc[0]["at_bats_per_home_run"] == "20.1"
    assert set(first_df["group"]) == {"hitting", "pitching"}


def test_load_stats_leaders_flattens_rank_and_person():
    payload = {
        "leagueLeaders": [
            {"leaders": [{"rank": 1, "value": "58", "person": {"id": 1, "fullName": "Player One"}}]}
        ]
    }
    with patch.object(mlb_api.statsapi, "get", return_value=payload):
        with patch.object(mlb_api, "load_dataframe") as mock_load:
            mlb_api._load_stats_leaders(object(), 2024)
    df = mock_load.call_args.args[2]
    assert set(df["leader_category"]) == set(mlb_api.LEADER_CATEGORIES)
    assert df.iloc[0]["rank"] == 1
    assert df.iloc[0]["person_name"] == "Player One"


def test_load_team_leaders_stamps_team_id_per_team():
    payload = {
        "teamLeaders": [
            {"leaders": [{"rank": 1, "value": "10", "person": {"id": 1, "fullName": "P"}}]}
        ]
    }
    with patch.object(mlb_api.statsapi, "get", return_value=payload):
        with patch.object(mlb_api, "_season_team_ids", return_value=[147]):
            with patch.object(mlb_api, "load_dataframe") as mock_load:
                mlb_api._load_team_leaders(object(), 2024)
    df = mock_load.call_args.args[2]
    assert set(df["team_id"]) == {147}


def test_load_awards_catalog_is_a_flat_reload_not_season_scoped():
    payload = {"awards": [{"id": "NLMVP", "name": "NL MVP"}, {"id": "ALMVP", "name": "AL MVP"}]}
    with patch.object(mlb_api.statsapi, "get", return_value=payload) as mock_get:
        with patch.object(mlb_api, "load_dataframe") as mock_load:
            mlb_api._load_awards_catalog(object())
    assert mock_get.call_args.kwargs.get("force") is True
    df = mock_load.call_args.args[2]
    assert len(df) == 2
    # No scope_column/scope_value kwargs — a full reload each run.
    assert "scope_column" not in mock_load.call_args.kwargs


def test_linescore_rows_flattens_one_row_per_inning_per_side():
    data = {
        "innings": [
            {
                "num": 1,
                "home": {"runs": 0, "hits": 0, "errors": 0, "leftOnBase": 0},
                "away": {"runs": 2, "hits": 1, "errors": 0, "leftOnBase": 1},
            }
        ]
    }
    rows = mlb_api._linescore_rows(data, 777)
    assert rows == [
        {
            "game_pk": 777,
            "inning": 1,
            "side": "home",
            "runs": 0,
            "hits": 0,
            "errors": 0,
            "left_on_base": 0,
        },
        {
            "game_pk": 777,
            "inning": 1,
            "side": "away",
            "runs": 2,
            "hits": 1,
            "errors": 0,
            "left_on_base": 1,
        },
    ]


def test_load_context_metrics_flattens_single_game_level_row():
    payload = {
        "game": {"gamePk": 777},
        "awayWinProbability": 53.6,
        "homeWinProbability": 46.4,
        "leftFieldSacFlyProbability": 0.5,
        "centerFieldSacFlyProbability": 0.6,
        "rightFieldSacFlyProbability": 0.7,
    }
    with patch.object(mlb_api.statsapi, "get", return_value=payload):
        with patch.object(mlb_api, "load_dataframe") as mock_load:
            mlb_api._load_context_metrics_for_game(object(), 777, 2024)
    df = mock_load.call_args.args[2]
    assert len(df) == 1
    assert df.iloc[0]["away_win_probability"] == 53.6
    assert df.iloc[0]["home_win_probability"] == 46.4
    assert df.iloc[0]["left_field_sac_fly_probability"] == 0.5
    assert df.iloc[0]["_season"] == "2024"


def test_load_analytics_for_game_covers_win_prob_linescore_and_context():
    with (
        patch.object(mlb_api, "_load_win_prob_for_game", return_value=5) as m1,
        patch.object(mlb_api, "_load_linescore_for_game", return_value=18) as m2,
        patch.object(mlb_api, "_load_context_metrics_for_game", return_value=1) as m3,
    ):
        counts = mlb_api._load_analytics_for_game(object(), 777, 2024)
    assert counts == {
        "raw.mlb_win_prob": 5,
        "raw.mlb_linescore": 18,
        "raw.mlb_game_context": 1,
    }
    assert m1.call_args.args[1:] == (777, 2024)
    assert m2.call_args.args[1:] == (777, 2024)
    assert m3.call_args.args[1:] == (777, 2024)


def test_job_roster_rows_flattens_person_and_job_fields():
    data = {
        "roster": [
            {
                "person": {"id": 1, "fullName": "Scorer One"},
                "jerseyNumber": "",
                "job": "Official Scorer",
                "jobId": "SCOR",
            }
        ]
    }
    assert mlb_api._job_roster_rows(data) == [
        {
            "person_id": 1,
            "person_name": "Scorer One",
            "jersey_number": "",
            "job": "Official Scorer",
            "job_id": "SCOR",
        }
    ]


def test_load_conferences_full_reload_not_scoped():
    payload = {"conferences": [{"id": 301, "name": "PCL American Conference"}]}
    with patch.object(mlb_api.statsapi, "get", return_value=payload) as mock_get:
        with patch.object(mlb_api, "load_dataframe") as mock_load:
            mlb_api._load_conferences(object())
    assert mock_get.call_args.kwargs.get("force") is True
    assert "scope_column" not in mock_load.call_args.kwargs


def test_load_datacasters_uses_job_roster_shape():
    payload = {
        "roster": [
            {"person": {"id": 9, "fullName": "Stringer One"}, "job": "Stringer", "jobId": "MSTR"}
        ]
    }
    with patch.object(mlb_api.statsapi, "get", return_value=payload):
        with patch.object(mlb_api, "load_dataframe") as mock_load:
            mlb_api._load_datacasters(object())
    df = mock_load.call_args.args[2]
    assert df.iloc[0]["person_name"] == "Stringer One"
    assert df.iloc[0]["job"] == "Stringer"


def test_probable_rows_only_includes_sides_with_an_announced_pitcher():
    # A game several days out often has no probablePitcher key at all on
    # one or both sides yet (confirmed directly against real 2026 data) --
    # this must skip those sides entirely, not emit a placeholder row.
    data = {
        "dates": [
            {
                "games": [
                    {
                        "gamePk": 1,
                        "teams": {
                            "home": {"probablePitcher": {"id": 100, "fullName": "Home Guy"}},
                            "away": {},
                        },
                    },
                    {
                        "gamePk": 2,
                        "teams": {"home": {}, "away": {}},
                    },
                ]
            }
        ]
    }
    assert mlb_api._probable_rows(data) == [
        {"game_pk": 1, "side": "home", "pitcher_id": 100, "pitcher_name": "Home Guy"}
    ]


def test_new_probable_rows_filters_out_unchanged_announcements():
    # update() re-fetches the identical days-ahead window every 5 minutes --
    # only a genuinely new (game_pk, side) or a changed pitcher_id (a
    # scratch, a rotation swap) should ever reach append_dataframe.
    rows = [
        {"game_pk": 1, "side": "home", "pitcher_id": 100, "pitcher_name": "Same"},
        {"game_pk": 1, "side": "away", "pitcher_id": 200, "pitcher_name": "Scratched In"},
        {"game_pk": 2, "side": "home", "pitcher_id": 300, "pitcher_name": "Brand New"},
    ]
    known = {("1", "home"): "100", ("1", "away"): "999"}  # away side changed: 999 -> 200
    assert mlb_api._new_probable_rows(rows, known) == [rows[1], rows[2]]


def test_new_probable_rows_returns_everything_when_nothing_known_yet():
    rows = [{"game_pk": 1, "side": "home", "pitcher_id": 100, "pitcher_name": "First Ever"}]
    assert mlb_api._new_probable_rows(rows, {}) == rows
