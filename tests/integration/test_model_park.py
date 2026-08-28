"""Regression coverage for mlb_baseball.model.park -- trailing-window
park factors and environmental weather features (ADR-035, PARK-01, WEA-01).
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
    # Season 2020: 12 home runs / 5 road runs -> 240.00
    # Season 2021: 8 home runs / 8 road runs -> 100.00
    # Season 2022: 14 home runs / 10 road runs -> 140.00
    # Target Season 2023:
    #   park_factor_1yr (2022) = 140.00
    #   park_factor_3yr (2020..2022) = (240 + 100 + 140)/3 = 160.00
    #   park_hr_factor_3yr = 160.00
    #   park_2b_factor_3yr = 100.0 + (160.0 - 100.0)*0.85 = 151.00
    #   park_3b_factor_3yr = 100.0 + (160.0 - 100.0)*0.70 = 142.00
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
            "INSERT INTO core.game ("
            "retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type, venue_id) VALUES "
            "('H1', 2020, '2020-04-01', %(atl)s, %(nya)s, 7, 5, 'regular', %(venue)s), "
            "('R1', 2020, '2020-04-05', %(bos)s, %(atl)s, 2, 3, 'regular', NULL), "
            "('H2', 2021, '2021-04-01', %(atl)s, %(nya)s, 4, 4, 'regular', %(venue)s), "
            "('R2', 2021, '2021-04-05', %(bos)s, %(atl)s, 5, 3, 'regular', NULL), "
            "('H3', 2022, '2022-04-01', %(atl)s, %(nya)s, 8, 6, 'regular', %(venue)s), "
            "('R3', 2022, '2022-04-05', %(bos)s, %(atl)s, 6, 4, 'regular', NULL), "
            "('T1', 2023, '2023-04-01', %(atl)s, %(nya)s, 1, 1, 'regular', %(venue)s)",
            {"atl": atl, "nya": nya, "bos": bos, "venue": venue_id},
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE gold.game_feature SET temp_f = 70, wind_speed_mph = 12, wind_dir = 'to cf' "
            "WHERE game_id = (SELECT id FROM core.game WHERE retro_game_id = 'T1')"
        )
    db_conn.commit()

    updated = park.compute(db_conn)
    db_conn.commit()

    assert updated >= 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.park_factor, f.park_factor_1yr, f.park_factor_3yr, "
            "       f.park_hr_factor_3yr, f.park_2b_factor_3yr, f.park_3b_factor_3yr, "
            "       f.air_density_index, f.effective_wind_speed, f.wind_direction_label "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "WHERE g.retro_game_id = 'T1'"
        )
        row = cur.fetchone()

    (
        retro_id,
        pf,
        pf_1yr,
        pf_3yr,
        pf_hr,
        pf_2b,
        pf_3b,
        air_density,
        eff_wind,
        wind_label,
    ) = row

    assert pf == Decimal("160.00")
    assert pf_1yr == Decimal("140.00")
    assert pf_3yr == Decimal("160.00")
    assert pf_hr == Decimal("160.00")
    assert pf_2b == Decimal("151.00")
    assert pf_3b == Decimal("142.00")
    assert air_density == Decimal("100.00")
    assert eff_wind == Decimal("12.0")
    assert wind_label == "outfield"

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
            "UPDATE gold.game_feature SET park_factor_3yr = 9999 "
            "WHERE game_id = (SELECT id FROM core.game WHERE retro_game_id = 'G1')"
        )
    db_conn.commit()

    check = park.health_check()[0]

    assert not check.ok
    assert "outside valid domain bounds" in check.detail

    _reset(db_conn)


def test_health_check_accepts_verified_small_sample_historical_extremes(db_conn):
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
            "UPDATE gold.game_feature SET park_factor_3yr = 290.00 "
            "WHERE game_id = (SELECT id FROM core.game WHERE retro_game_id = 'G1')"
        )
        cur.execute(
            "UPDATE gold.game_feature SET park_factor_3yr = 33.33 "
            "WHERE game_id = (SELECT id FROM core.game WHERE retro_game_id = 'G2')"
        )
    db_conn.commit()

    check = park.health_check()[0]

    assert check.ok

    _reset(db_conn)
