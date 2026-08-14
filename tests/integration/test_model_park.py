"""Regression coverage for mlb_baseball.model.park -- trailing-window
park factor (ADR-035).
"""

from decimal import Decimal

from mlb_baseball.model import features, park


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.venue")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_compute_matches_hand_calculation_and_stays_out_of_its_own_trailing_window(db_conn):
    # ATL's only home game at venue V (season 2020): 7+5=12 total runs.
    # ATL's only road game that season: 2+3=5 total runs.
    # park_factor(V, 2020) = 100 * 12/5 = 240 -- but only usable for a
    # LATER season's trailing window (2020 falls in [2023-3, 2023-1]),
    # never for 2020 itself: no leakage into the season that produced it.
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 2025, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147), "
            "('BOS', 'Boston', 'Red Sox', 1901, 2025, 111) "
            "RETURNING id, retro_team_id"
        )
        teams = {retro_id: team_id for team_id, retro_id in cur.fetchall()}
        atl, nya, bos = teams["ATL"], teams["NYA"], teams["BOS"]
        cur.execute(
            "INSERT INTO core.venue (retro_park_id, name, mlb_venue_id) "
            "VALUES ('ATL03', 'Truist Park', 4705) RETURNING id"
        )
        (venue_id,) = cur.fetchone()
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type, venue_id) VALUES "
            "('H1', 2020, '2020-04-01', %(atl)s, %(nya)s, 7, 5, 'regular', %(venue)s), "
            "('R1', 2020, '2020-04-05', %(bos)s, %(atl)s, 2, 3, 'regular', NULL), "
            "('T1', 2023, '2023-04-01', %(atl)s, %(nya)s, 1, 1, 'regular', %(venue)s)",
            {"atl": atl, "nya": nya, "bos": bos, "venue": venue_id},
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = park.compute(db_conn)
    db_conn.commit()

    assert updated == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.park_factor "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1] for r in cur.fetchall()}

    assert rows["H1"] is None  # no trailing window yet -- this game IS the source data
    assert rows["R1"] is None  # a road game -- never gets a park_factor at all
    assert rows["T1"] == Decimal("240.00000000000000000")

    _reset(db_conn)


def test_health_check_flags_an_implausible_value(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 2025, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147) "
            "RETURNING id, retro_team_id"
        )
        teams = {retro_id: team_id for team_id, retro_id in cur.fetchall()}
        atl, nya = teams["ATL"], teams["NYA"]
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
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE gold.game_feature SET park_factor = 9999 "
            "WHERE game_id = (SELECT id FROM core.game WHERE retro_game_id = 'G1')"
        )
    db_conn.commit()

    check = park.health_check()[0]

    assert not check.ok
    assert "1 rows" in check.detail

    _reset(db_conn)


def test_health_check_accepts_verified_small_sample_historical_extremes(db_conn):
    # Real production values, not synthetic: venue 1604 ("South Side Park
    # III") was the Chicago American Giants' (a Negro League team) home
    # park 1913-1940, with as few as 1-11 games/season -- a legitimately
    # noisy trailing-window ratio, not a bug. Confirmed by hand against
    # production on 2026-08-14: the real full range across all 207,279
    # non-null park_factor rows is exactly 33.33-290.00 (see park.py's
    # health_check docstring). Both must stay inside the health check's
    # bound; a genuine computation bug (inverted ratio) would produce
    # something near 0 or in the thousands, which the next test covers.
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 2025, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147) "
            "RETURNING id, retro_team_id"
        )
        teams = {retro_id: team_id for team_id, retro_id in cur.fetchall()}
        atl, nya = teams["ATL"], teams["NYA"]
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 1926, '1926-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', 1929, '1929-04-01', %(nya)s, %(atl)s, 5, 3, 'regular')",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()
    features.build(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE gold.game_feature SET park_factor = 290.00 "
            "WHERE game_id = (SELECT id FROM core.game WHERE retro_game_id = 'G1')"
        )
        cur.execute(
            "UPDATE gold.game_feature SET park_factor = 33.33 "
            "WHERE game_id = (SELECT id FROM core.game WHERE retro_game_id = 'G2')"
        )
    db_conn.commit()

    check = park.health_check()[0]

    assert check.ok

    _reset(db_conn)
