"""Regression coverage for mlb_baseball.model.diff -- home-minus-away
interaction terms (ADR-081, admission queue INT-01). Pure algebra over
already-populated gold.game_feature columns, so these tests seed
gold.game_feature directly rather than running the full features.build()
pipeline -- diff.py has no raw-table or core.game dependency at all.
"""

from decimal import Decimal

from mlb_baseball.model import diff


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
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(season, game_date, home_team_id, away_team_id, game_instance_key, "
            "home_win_pct, away_win_pct, home_win_pct_10, away_win_pct_10, "
            "home_pyth_wpct, away_pyth_wpct, home_elo, away_elo, "
            "home_woba, away_woba, home_wrc_plus, away_wrc_plus) VALUES "
            "(2024, '2024-04-01', %(atl)s, %(nya)s, 'diff-test:G1', "
            "0.600, 0.400, 0.700, 0.300, 0.550, 0.450, 1550, 1450, "
            "0.340, 0.310, 110, 95)",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()

    updated = diff.compute(db_conn)
    db_conn.commit()

    assert updated == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT win_pct_diff, win_pct_10_diff, pyth_wpct_diff, elo_diff, "
            "woba_diff, wrc_plus_diff "
            "FROM gold.game_feature WHERE game_instance_key = 'diff-test:G1'"
        )
        row = cur.fetchone()

    assert row == (
        Decimal("0.200"),
        Decimal("0.400"),
        Decimal("0.100"),
        Decimal("100"),
        Decimal("0.030"),
        Decimal("15"),
    )


def test_compute_is_null_when_either_side_is_unavailable(db_conn):
    # A completely unenriched row (nothing beyond the base insert) must
    # produce NULL diffs, not an error or a false zero -- subtracting a
    # NULL is NULL in SQL, exercised here against a real row rather than
    # assumed.
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(season, game_date, home_team_id, away_team_id, game_instance_key, "
            "home_elo, away_elo) VALUES "
            "(2024, '2024-04-01', %(atl)s, %(nya)s, 'diff-test:G2', 1500, NULL)",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()

    diff.compute(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT win_pct_diff, elo_diff FROM gold.game_feature "
            "WHERE game_instance_key = 'diff-test:G2'"
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
            "home_elo, away_elo) VALUES "
            "(2024, '2024-04-01', %(atl)s, %(nya)s, 'diff-test:G3', 1600, 1400)",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()

    diff.compute(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT elo_diff FROM gold.game_feature WHERE game_instance_key = 'diff-test:G3'"
        )
        (first,) = cur.fetchone()

    diff.compute(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT elo_diff FROM gold.game_feature WHERE game_instance_key = 'diff-test:G3'"
        )
        (second,) = cur.fetchone()

    assert first == second == Decimal("200")


def test_health_check_flags_a_parity_violation(db_conn):
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(season, game_date, home_team_id, away_team_id, game_instance_key, "
            "home_elo, away_elo, elo_diff) VALUES "
            "(2024, '2024-04-01', %(atl)s, %(nya)s, 'diff-test:G4', 1600, 1400, 999)",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()

    checks = diff.health_check()
    elo_check = next(c for c in checks if c.name == "elo_diff")

    assert not elo_check.ok
    assert "1 rows" in elo_check.detail


def test_health_check_passes_after_a_real_compute(db_conn):
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(season, game_date, home_team_id, away_team_id, game_instance_key, "
            "home_elo, away_elo) VALUES "
            "(2024, '2024-04-01', %(atl)s, %(nya)s, 'diff-test:G5', 1600, 1400)",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()
    diff.compute(db_conn)
    db_conn.commit()

    checks = diff.health_check()

    assert all(c.ok for c in checks)
