"""Regression coverage for mlb_baseball.model.elo's DB-facing pieces
(compute_ratings/predict) -- the pure formulas are unit-tested in
tests/unit/test_elo_formula.py.
"""

from decimal import Decimal

from mlb_baseball.model import elo, features


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
                "status text, home_id text, away_id text, game_num text, "
                "venue_id text)"
            )
    db_conn.commit()


def _reset(db_conn):
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


def test_compute_ratings_starts_at_1500_and_updates_after_a_decided_game(db_conn):
    # Hand-verified: expected_win_prob(1500, 1500) = 0.5344839..., mult
    # for a 2-run home win at those ratings = 0.4740840..., giving
    # new_home = 1500.882774908366, new_away = 1499.117225091634.
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2024, '2024-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', 2024, '2024-04-02', %(atl)s, %(nya)s, 2, 1, 'regular')",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    count = elo.compute_ratings(db_conn)
    db_conn.commit()

    assert count == 2
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_elo, f.away_elo "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    assert rows["G1"] == (Decimal("1500"), Decimal("1500"))
    home_elo, away_elo = rows["G2"]
    assert abs(home_elo - Decimal("1500.8828")) < Decimal("0.001")
    assert abs(away_elo - Decimal("1499.1172")) < Decimal("0.001")

    _reset(db_conn)


def test_predict_uses_computed_ratings_for_upcoming_game(db_conn):
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
        # ATL won G1 -- entering G2, ATL's rating should be above 1500,
        # so ATL (home again) should be favored by more than a coin flip
        # plus bare home-field advantage alone would give.
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, _season, game_date, game_type, status, home_id, away_id, game_num) "
            "VALUES ('999004', '2024', '2024-04-02', 'R', 'Scheduled', '144', '147', '1')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    elo.compute_ratings(db_conn)
    db_conn.commit()
    inserted = elo.predict(db_conn)
    db_conn.commit()

    assert inserted == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_win_prob, model_version FROM gold.prediction WHERE mlb_game_pk = '999004'"
        )
        home_win_prob, model_version = cur.fetchone()
    assert model_version == "elo-v1"
    assert home_win_prob > Decimal("0.53")  # bare home-field-advantage floor from a 1500/1500 game
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT p.model_id, r.run_type, r.status FROM gold.prediction p "
            "JOIN meta.model_run r ON r.run_id = p.model_run_id "
            "WHERE p.mlb_game_pk = '999004'"
        )
        _model_id, run_type, status = cur.fetchone()
    assert (run_type, status) == ("predict", "success")

    _reset(db_conn)


def test_rerunning_compute_ratings_is_idempotent(db_conn):
    _reset(db_conn)


def test_compute_ratings_uses_declared_doubleheader_order_not_feature_row_id(db_conn):
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2024, '2024-04-01', %s, %s, 5, 3, 'regular'), "
            "('G2', 2024, '2024-04-01', %s, %s, 2, 1, 'regular') "
            "RETURNING id, retro_game_id",
            (atl, nya, atl, nya),
        )
        games = {retro_id: game_id for game_id, retro_id in cur.fetchall()}
        # Insert game two first so its surrogate feature ID is lower. The
        # declared doubleheader number must still make game one update Elo
        # before game two.
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(game_id, game_instance_key, season, game_date, game_number, feature_cutoff_at, "
            "mlb_game_pk, home_team_id, away_team_id, home_win) "
            "VALUES (%s, 'mlb:2', 2024, '2024-04-01', 2, '2024-04-01 19:00+00', "
            "'2', %s, %s, true), "
            "(%s, 'mlb:1', 2024, '2024-04-01', 1, '2024-04-01 13:00+00', "
            "'1', %s, %s, true)",
            (games["G2"], atl, nya, games["G1"], atl, nya),
        )
    db_conn.commit()

    elo.compute_ratings(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_elo FROM gold.game_feature WHERE game_instance_key = 'mlb:2'"
        )
        (second_game_home_elo,) = cur.fetchone()
    assert second_game_home_elo > Decimal("1500")

    _reset(db_conn)
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
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    elo.compute_ratings(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute("SELECT home_elo, away_elo FROM gold.game_feature")
        first = cur.fetchone()

    # Re-running features.build() truncates and rebuilds gold.game_feature
    # (home_elo/away_elo reset to NULL), then compute_ratings() must walk
    # the full history again from scratch and land on the exact same
    # numbers -- not drift from running twice.
    features.build(db_conn)
    db_conn.commit()
    elo.compute_ratings(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute("SELECT home_elo, away_elo FROM gold.game_feature")
        second = cur.fetchone()

    assert first == second == (Decimal("1500"), Decimal("1500"))

    _reset(db_conn)
