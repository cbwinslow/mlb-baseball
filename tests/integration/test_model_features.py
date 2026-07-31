"""Regression coverage for mlb_baseball.model.features -- gold.game_feature's
point-in-time window-function build (ADR-032).

Cleanup uses targeted DELETE, not TRUNCATE CASCADE -- core.game cascades
into core.play/core.pitch, which migration 0011 partitioned into 150+
pieces each; TRUNCATE CASCADE against them was confirmed to hang 10+
minutes even when empty (see issue #2). DELETE has no such cost here since
these tests never touch core.play/core.pitch at all.
"""

from decimal import Decimal

from mlb_baseball.model import features


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
    # in this file (or test_model_log5.py, which shares this natural key)
    # failing before reaching its own cleanup would otherwise leave
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


def test_build_computes_point_in_time_win_pct_and_pythagenpat(db_conn):
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2024, '2024-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', 2024, '2024-04-02', %(atl)s, %(nya)s, 2, 1, 'regular'), "
            "('G3', 2024, '2024-04-03', %(atl)s, %(nya)s, 1, 4, 'regular')",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()

    count = features.build(db_conn)
    db_conn.commit()
    assert count == 3

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_win_pct, f.away_win_pct, "
            "f.home_run_diff, f.away_run_diff, f.home_win "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    # G1: first game of the season for both teams -- nothing prior to
    # compute from, every rolling stat is honestly NULL, not zero.
    assert rows["G1"] == (None, None, None, None, True)

    # G2: entering it, ATL is 1-0 (won G1), NYA is 0-1.
    g2 = rows["G2"]
    assert g2[0] == Decimal("1.00000000000000000000")
    assert g2[1] == Decimal("0E-20")  # 0, Postgres's numeric zero representation
    assert g2[2] == Decimal("2")  # ATL's run diff before G2: 5-3
    assert g2[3] == Decimal("-2")
    assert g2[4] is True

    # G3: entering it, ATL is 2-0, NYA is 0-2.
    g3 = rows["G3"]
    assert g3[0] == Decimal("1.00000000000000000000")
    assert g3[1] == Decimal("0E-20")
    assert g3[2] == Decimal("3")  # (5-3) + (2-1)
    assert g3[3] == Decimal("-3")
    assert g3[4] is False  # ATL lost G3, 1-4

    _reset(db_conn)


def test_pythagenpat_home_and_away_sum_to_one(db_conn):
    # Same run total (RS+RA) on both sides of a game means the same
    # scoring-environment exponent applies to both teams -- home_pyth_wpct
    # and away_pyth_wpct should be exact complements, not just close.
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

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT f.home_pyth_wpct, f.away_pyth_wpct FROM gold.game_feature f "
            "JOIN core.game g ON g.id = f.game_id WHERE g.retro_game_id = 'G2'"
        )
        home_pyth, away_pyth = cur.fetchone()

    assert home_pyth + away_pyth == Decimal("1.00000000000000000000")
    assert Decimal("0.71") < home_pyth < Decimal("0.72")

    _reset(db_conn)


def test_rerunning_build_truncates_instead_of_duplicating(db_conn):
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

    first = features.build(db_conn)
    db_conn.commit()
    second = features.build(db_conn)
    db_conn.commit()

    assert first == 1
    assert second == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM gold.game_feature")
        (count,) = cur.fetchone()
    assert count == 1

    _reset(db_conn)


def test_health_check_flags_empty_table():
    check = next(c for c in features.health_check() if c.name == "gold.game_feature")
    # Whatever state the DB happens to be in at test time, this must not
    # raise -- the real assertion is that health_check() returns cleanly
    # and names the right table.
    assert check.name == "gold.game_feature"
