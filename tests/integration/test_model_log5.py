"""Regression coverage for mlb_baseball.model.log5's DB-facing pieces
(predict/backfill_outcomes) -- the pure formula itself is unit-tested in
tests/unit/test_log5_formula.py.

Undecided games are seeded via raw.mlb_schedule, not core.game directly --
core.game only ever holds completed games (conform.py's _build_games
excludes status = 'Scheduled', see migration 0014), so that's the only
path an undecided game can realistically take in production.
"""

from decimal import Decimal

from mlb_baseball.model import features, log5


def _seed_teams(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 2025, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147) "
            "RETURNING id, retro_team_id"
        )
        return {retro_id: team_id for team_id, retro_id in cur.fetchall()}


def _ensure_mlb_schedule_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        (exists,) = cur.fetchone()
        if not exists:
            cur.execute(
                "CREATE TABLE raw.mlb_schedule ("
                "game_id text, _season text, game_date text, game_type text, "
                "status text, home_id text, away_id text, game_num text)"
            )
    db_conn.commit()


def _reset(db_conn):
    # Called at both the start and end of every test here -- a prior test
    # (in this file or test_model_features.py, which shares this natural
    # key) failing before reaching its own cleanup would otherwise leave
    # ATL/NYA rows behind and collide with the next test's _seed_teams
    # insert. Same defensive-reset pattern as test_conform.py's
    # _reset_dynamic_tables().
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        (schedule_exists,) = cur.fetchone()
        if schedule_exists:
            cur.execute("DELETE FROM raw.mlb_schedule")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_predict_skips_decided_games_and_season_openers(db_conn):
    _reset(db_conn)
    _ensure_mlb_schedule_table(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            # G1: season opener for both -- no win_pct yet, must be skipped.
            "('G1', 2024, '2024-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            # G2: decided already (has a score) -- must be skipped, only
            # upcoming games get predictions from predict().
            "('G2', 2024, '2024-04-02', %(atl)s, %(nya)s, 2, 1, 'regular')",
            {"atl": atl, "nya": nya},
        )
        # G3: not yet decided, sourced from raw.mlb_schedule -- the only
        # one that should get a prediction.
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, _season, game_date, game_type, status, home_id, away_id, game_num) "
            "VALUES ('999001', '2024', '2024-04-03', 'R', 'Scheduled', '144', '147', '1')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    inserted = log5.predict(db_conn)
    db_conn.commit()

    assert inserted == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT mlb_game_pk, home_win_prob, model_version, actual_home_win FROM gold.prediction"
        )
        rows = cur.fetchall()
    assert len(rows) == 1
    mlb_game_pk, home_win_prob, model_version, actual = rows[0]
    assert mlb_game_pk == "999001"
    assert model_version == "log5-v1"
    assert actual is None
    # ATL entered 2-0, NYA 0-2 -- log5(1.0, 0.0) is exactly 1, not merely
    # "greater than 0.5" (verified separately in tests/unit/test_log5_formula.py).
    assert home_win_prob == Decimal("1")

    _reset(db_conn)


def test_backfill_outcomes_fills_in_actual_result_once_game_is_final(db_conn):
    _reset(db_conn)
    _ensure_mlb_schedule_table(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) "
            "VALUES ('G1', 2024, '2024-04-01', %s, %s, 5, 3, 'regular')",
            (atl, nya),
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, _season, game_date, game_type, status, home_id, away_id, game_num) "
            "VALUES ('999002', '2024', '2024-04-02', 'R', 'Scheduled', '144', '147', '1')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    log5.predict(db_conn)
    db_conn.commit()

    # Game 999002 now finishes, 4-2 to the away team (NYA wins) -- conform
    # would normally land this in core.game with game_pk backfilled to the
    # same value raw.mlb_schedule always had for it; simulated directly
    # here rather than re-running the full conform pipeline in a test.
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type, game_pk) "
            "VALUES ('G2', 2024, '2024-04-02', %s, %s, 2, 4, 'regular', '999002')",
            (atl, nya),
        )
    db_conn.commit()

    updated = log5.backfill_outcomes(db_conn)
    db_conn.commit()

    assert updated == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT actual_home_win FROM gold.prediction WHERE mlb_game_pk = '999002'"
        )
        (actual,) = cur.fetchone()
    assert actual is False  # home team (ATL) lost, 2-4

    _reset(db_conn)


def test_rerunning_predict_before_game_day_preserves_prediction_history(db_conn):
    # gold.prediction is deliberately history-preserving (migration 0013)
    # -- re-running predict() for the same still-undecided game before it's
    # played should add another row, not overwrite/skip the first one.
    _reset(db_conn)
    _ensure_mlb_schedule_table(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) "
            "VALUES ('G1', 2024, '2024-04-01', %s, %s, 5, 3, 'regular')",
            (atl, nya),
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, _season, game_date, game_type, status, home_id, away_id, game_num) "
            "VALUES ('999003', '2024', '2024-04-02', 'R', 'Scheduled', '144', '147', '1')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    first = log5.predict(db_conn)
    db_conn.commit()
    second = log5.predict(db_conn)
    db_conn.commit()

    assert first == 1
    assert second == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM gold.prediction")
        (count,) = cur.fetchone()
    assert count == 2

    _reset(db_conn)
