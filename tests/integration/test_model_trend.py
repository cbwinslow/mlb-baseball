"""Regression coverage for mlb_baseball.model.trend -- recent-minus-long
win-rate trend (ADR-083, admission queue INT-02). Pure algebra over
already-populated gold.game_feature columns, so these tests seed
gold.game_feature directly rather than running the full features.build()
pipeline -- trend.py has no raw-table or core.game dependency at all.
"""

from decimal import Decimal

from mlb_baseball.model import trend


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.team")
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
        return {retro_id: team_id for team_id, retro_id in cur.fetchall()}


def test_compute_matches_hand_calculation(db_conn):
    # ATL playing much better recently than its season rate (0.800 - 0.500
    # = +0.300); NYA playing worse (0.200 - 0.500 = -0.300).
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(season, game_date, home_team_id, away_team_id, game_instance_key, "
            "home_win_pct, home_win_pct_10, away_win_pct, away_win_pct_10) VALUES "
            "(2024, '2024-04-01', %(atl)s, %(nya)s, 'trend-test:G1', "
            "0.500, 0.800, 0.500, 0.200)",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()

    updated = trend.compute(db_conn)
    db_conn.commit()

    assert updated == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_win_pct_trend, away_win_pct_trend "
            "FROM gold.game_feature WHERE game_instance_key = 'trend-test:G1'"
        )
        row = cur.fetchone()

    assert row == (Decimal("0.300"), Decimal("-0.300"))


def test_compute_is_null_when_either_window_is_unavailable(db_conn):
    # A team's first game of the season has NULL win_pct/win_pct_10 (no
    # prior games at all) -- the trend must stay NULL, not error or
    # silently default to zero.
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(season, game_date, home_team_id, away_team_id, game_instance_key) VALUES "
            "(2024, '2024-04-01', %(atl)s, %(nya)s, 'trend-test:G2')",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()

    trend.compute(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_win_pct_trend, away_win_pct_trend "
            "FROM gold.game_feature WHERE game_instance_key = 'trend-test:G2'"
        )
        row = cur.fetchone()

    assert row == (None, None)


def test_compute_is_idempotent(db_conn):
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(season, game_date, home_team_id, away_team_id, game_instance_key, "
            "home_win_pct, home_win_pct_10) VALUES "
            "(2024, '2024-04-01', %(atl)s, %(nya)s, 'trend-test:G3', 0.400, 0.600)",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()

    trend.compute(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_win_pct_trend FROM gold.game_feature "
            "WHERE game_instance_key = 'trend-test:G3'"
        )
        (first,) = cur.fetchone()

    trend.compute(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_win_pct_trend FROM gold.game_feature "
            "WHERE game_instance_key = 'trend-test:G3'"
        )
        (second,) = cur.fetchone()

    assert first == second == Decimal("0.200")


def test_health_check_flags_a_parity_violation(db_conn):
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(season, game_date, home_team_id, away_team_id, game_instance_key, "
            "home_win_pct, home_win_pct_10, home_win_pct_trend) VALUES "
            "(2024, '2024-04-01', %(atl)s, %(nya)s, 'trend-test:G4', 0.400, 0.600, 999)",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()

    checks = trend.health_check()
    home_check = next(c for c in checks if c.name == "home_win_pct_trend")

    assert not home_check.ok
    assert "1 rows" in home_check.detail


def test_health_check_passes_after_a_real_compute(db_conn):
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(season, game_date, home_team_id, away_team_id, game_instance_key, "
            "home_win_pct, home_win_pct_10) VALUES "
            "(2024, '2024-04-01', %(atl)s, %(nya)s, 'trend-test:G5', 0.400, 0.600)",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()
    trend.compute(db_conn)
    db_conn.commit()

    checks = trend.health_check()

    assert all(c.ok for c in checks)
