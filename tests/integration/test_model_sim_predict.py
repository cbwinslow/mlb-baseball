"""Upcoming-game markov-v1 writer (ADR-272). Uses mlb_test."""

from datetime import date

import pytest

from mlb_baseball.model import sim_predict


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gameinfo")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.player")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


@pytest.fixture(autouse=True)
def _clean(db_conn):
    _reset(db_conn)
    yield
    _reset(db_conn)


def _ensure_retrosheet(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_event ("
            "game_id text, inn_ct text, bat_home_id text, "
            "outs_ct text, event_outs_ct text, event_cd text, "
            "base1_run_id text, base2_run_id text, base3_run_id text, "
            "bat_dest_id text, run1_dest_id text, run2_dest_id text, "
            "run3_dest_id text, resp_pit_id text, bat_event_fl text)"
        )
        cur.execute(
            "CREATE TABLE raw.retrosheet_gameinfo ("
            "gid text, gametype text, _season text, visteam text, hometeam text, "
            "date text)"
        )
    db_conn.commit()


def _seed_teams(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 2025, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147) "
            "RETURNING id, retro_team_id"
        )
        return {retro: team_id for team_id, retro in cur.fetchall()}


def _insert_event(cur, gid, *, bat_home_id, bat_dest, event_cd="23"):
    cur.execute(
        "INSERT INTO raw.retrosheet_event "
        "(game_id, inn_ct, bat_home_id, outs_ct, event_outs_ct, event_cd, "
        "base1_run_id, base2_run_id, base3_run_id, bat_dest_id, "
        "run1_dest_id, run2_dest_id, run3_dest_id, bat_event_fl) "
        "VALUES (%s, '1', %s, '0', '3', %s, NULL, NULL, NULL, %s, "
        "'0', '0', '0', 'T')",
        (gid, bat_home_id, event_cd, bat_dest),
    )


def test_predict_skips_decided_games_and_missing_retrosheet(db_conn):
    teams = _seed_teams(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(mlb_game_pk, game_instance_key, season, game_date, "
            "home_team_id, away_team_id, home_win) VALUES "
            "('1', 'mlb:1', 2024, '2024-07-01', %s, %s, TRUE), "
            "('2', 'mlb:2', 2024, '2024-07-02', %s, %s, NULL)",
            (teams["ATL"], teams["NYA"], teams["ATL"], teams["NYA"]),
        )
    db_conn.commit()
    assert sim_predict.predict(db_conn, n_games=10) == 0


def test_predict_writes_markov_v1_for_upcoming_games_only(db_conn):
    # 2023 NYA@ATL-shaped: ATL (away then, batting visteam) always HR;
    # NYA (home) always three-out. Upcoming 2024 ATL home vs NYA should
    # then have ATL as the scoring side and a home win rate above 0.5.
    _ensure_retrosheet(db_conn)
    teams = _seed_teams(db_conn)
    gid = "NYA202304010"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo "
            "(gid, gametype, _season, visteam, hometeam, date) "
            "VALUES (%s, 'regular', '2023', 'ATL', 'NYA', '20230401')",
            (gid,),
        )
        _insert_event(cur, gid, bat_home_id="0", bat_dest="4", event_cd="23")
        _insert_event(cur, gid, bat_home_id="1", bat_dest="0", event_cd="2")
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(mlb_game_pk, game_instance_key, season, game_date, "
            "home_team_id, away_team_id, home_win) VALUES "
            "('decided', 'mlb:decided', 2024, '2024-06-30', %s, %s, TRUE), "
            "('718001', 'mlb:718001', 2024, '2024-07-01', %s, %s, NULL)",
            (teams["ATL"], teams["NYA"], teams["ATL"], teams["NYA"]),
        )
    db_conn.commit()

    inserted = sim_predict.predict(db_conn, n_games=40)
    db_conn.commit()
    assert inserted == 1

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT mlb_game_pk, model_version, home_win_prob, actual_home_win FROM gold.prediction"
        )
        rows = cur.fetchall()
    assert len(rows) == 1
    pk, version, prob, actual = rows[0]
    assert pk == "718001"
    assert version == "markov-v1"
    assert actual is None
    assert float(prob) > 0.5

    again = sim_predict.predict(db_conn, n_games=40)
    db_conn.commit()
    assert again == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM gold.prediction WHERE model_version = 'markov-v1'")
        (count,) = cur.fetchone()
    assert count == 2


def test_predict_is_deterministic_for_a_game_pk(db_conn):
    _ensure_retrosheet(db_conn)
    teams = _seed_teams(db_conn)
    gid = "NYA202304010"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo "
            "(gid, gametype, _season, visteam, hometeam, date) "
            "VALUES (%s, 'regular', '2023', 'ATL', 'NYA', '20230401')",
            (gid,),
        )
        _insert_event(cur, gid, bat_home_id="0", bat_dest="4")
        _insert_event(cur, gid, bat_home_id="1", bat_dest="0", event_cd="2")
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(mlb_game_pk, game_instance_key, season, game_date, "
            "home_team_id, away_team_id, home_win) "
            "VALUES ('718001', 'mlb:718001', 2024, '2024-07-01', %s, %s, NULL)",
            (teams["ATL"], teams["NYA"]),
        )
    db_conn.commit()
    first = sim_predict.predict(db_conn, n_games=40)
    db_conn.commit()
    second = sim_predict.predict(db_conn, n_games=40)
    db_conn.commit()
    assert first == second == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_win_prob FROM gold.prediction "
            "WHERE model_version = 'markov-v1' ORDER BY generated_at"
        )
        probs = [row[0] for row in cur.fetchall()]
    assert probs[0] == probs[1]


def test_seasons_lookback_does_not_use_a_later_season_event(db_conn):
    # A 2025 event must not enter a 2024 upcoming game's prior.
    _ensure_retrosheet(db_conn)
    teams = _seed_teams(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo "
            "(gid, gametype, _season, visteam, hometeam, date) VALUES "
            "('NYA202304010', 'regular', '2023', 'ATL', 'NYA', '20230401'), "
            "('NYA202504010', 'regular', '2025', 'ATL', 'NYA', '20250401')"
        )
        _insert_event(cur, "NYA202304010", bat_home_id="0", bat_dest="4")
        _insert_event(cur, "NYA202304010", bat_home_id="1", bat_dest="0", event_cd="2")
        _insert_event(cur, "NYA202504010", bat_home_id="0", bat_dest="0", event_cd="2")
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(mlb_game_pk, game_instance_key, season, game_date, "
            "home_team_id, away_team_id, home_win) "
            "VALUES ('718001', 'mlb:718001', 2024, '2024-07-01', %s, %s, NULL)",
            (teams["ATL"], teams["NYA"]),
        )
    db_conn.commit()
    sim_predict.predict(db_conn, n_games=40)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute("SELECT home_win_prob FROM gold.prediction WHERE mlb_game_pk = '718001'")
        (prob,) = cur.fetchone()
    assert float(prob) > 0.5


def test_simulate_matchup_returns_none_without_a_cutoff_league_prior(db_conn):
    _ensure_retrosheet(db_conn)
    _seed_teams(db_conn)
    # Empty Retrosheet tables -> no league prior -> None, not a fake 0.5.
    result = sim_predict.simulate_matchup(
        db_conn,
        mlb_game_pk="718001",
        season=2024,
        game_date=date(2024, 7, 1),
        home_team="ATL",
        away_team="NYA",
        home_starter=None,
        away_starter=None,
        league_cache={},
        n_games=20,
    )
    assert result is None


def test_simulate_matchup_scores_a_fixture_game_deterministically(db_conn):
    _ensure_retrosheet(db_conn)
    _seed_teams(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo "
            "(gid, gametype, _season, visteam, hometeam, date) "
            "VALUES ('NYA202304010', 'regular', '2023', 'ATL', 'NYA', '20230401')"
        )
        _insert_event(cur, "NYA202304010", bat_home_id="0", bat_dest="4")
        _insert_event(cur, "NYA202304010", bat_home_id="1", bat_dest="0", event_cd="2")
    db_conn.commit()

    kwargs = {
        "mlb_game_pk": "718001",
        "season": 2024,
        "game_date": date(2024, 7, 1),
        "home_team": "ATL",
        "away_team": "NYA",
        "home_starter": None,
        "away_starter": None,
        "n_games": 40,
    }
    first = sim_predict.simulate_matchup(db_conn, league_cache={}, **kwargs)
    second = sim_predict.simulate_matchup(db_conn, league_cache={}, **kwargs)
    assert first is not None
    assert 0.0 <= first <= 1.0
    assert first == second  # seeded by mlb_game_pk
