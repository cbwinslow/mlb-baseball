"""Regression coverage for mlb_baseball.model.log5's DB-facing pieces
(predict/backfill_outcomes) -- the pure formula itself is unit-tested in
tests/unit/test_model_log5.py.
"""

from decimal import Decimal

from mlb_baseball.model import features, log5


def _seed_teams(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team (retro_team_id, city, nickname, first_year, last_year) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 2025), "
            "('NYA', 'New York', 'Yankees', 1913, 2025) "
            "RETURNING id, retro_team_id"
        )
        return {retro_id: team_id for team_id, retro_id in cur.fetchall()}


def _reset(db_conn):
    # Called at both the start and end of every test here -- a prior test
    # (in this file or test_model_features.py, which shares this natural
    # key) failing before reaching its own cleanup would otherwise leave
    # ATL/NYA rows behind and collide with the next test's _seed_teams
    # insert. Same defensive-reset pattern as test_conform.py's
    # _reset_dynamic_tables().
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_predict_skips_decided_games_and_season_openers(db_conn):
    _reset(db_conn)
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
            "('G2', 2024, '2024-04-02', %(atl)s, %(nya)s, 2, 1, 'regular'), "
            # G3: not yet decided (no score) -- the only one that should
            # get a prediction.
            "('G3', 2024, '2024-04-03', %(atl)s, %(nya)s, NULL, NULL, 'regular')",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    inserted = log5.predict(db_conn)
    db_conn.commit()

    assert inserted == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, p.home_win_prob, p.model_version, p.actual_home_win "
            "FROM gold.prediction p JOIN core.game g ON g.id = p.game_id"
        )
        rows = cur.fetchall()
    assert len(rows) == 1
    retro_id, home_win_prob, model_version, actual = rows[0]
    assert retro_id == "G3"
    assert model_version == "log5-v1"
    assert actual is None
    # ATL entered 2-0, NYA 0-2 -- log5(1.0, 0.0) is exactly 1, not merely
    # "greater than 0.5" (verified separately in tests/unit/test_log5_formula.py).
    assert home_win_prob == Decimal("1")

    _reset(db_conn)


def test_backfill_outcomes_fills_in_actual_result_once_game_is_final(db_conn):
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2024, '2024-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', 2024, '2024-04-02', %(atl)s, %(nya)s, NULL, NULL, 'regular') "
            "RETURNING id, retro_game_id",
            {"atl": atl, "nya": nya},
        )
        game_ids = {retro_id: game_id for game_id, retro_id in cur.fetchall()}
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    log5.predict(db_conn)
    db_conn.commit()

    # Game G2 now finishes, 4-2 to the away team (NYA wins).
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE core.game SET home_score = 2, away_score = 4 WHERE id = %s",
            (game_ids["G2"],),
        )
    db_conn.commit()

    updated = log5.backfill_outcomes(db_conn)
    db_conn.commit()

    assert updated == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT actual_home_win FROM gold.prediction WHERE game_id = %s",
            (game_ids["G2"],),
        )
        (actual,) = cur.fetchone()
    assert actual is False  # home team (ATL) lost, 2-4

    _reset(db_conn)


def test_rerunning_predict_before_game_day_preserves_prediction_history(db_conn):
    # gold.prediction is deliberately history-preserving (migration 0013)
    # -- re-running predict() for the same still-undecided game before it's
    # played should add another row, not overwrite/skip the first one.
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2024, '2024-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', 2024, '2024-04-02', %(atl)s, %(nya)s, NULL, NULL, 'regular')",
            {"atl": atl, "nya": nya},
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
