"""Regression coverage for mlb_baseball.model.pitch_movement -- pitch movement,
vertical separation, spin rates, and batter attack zone discipline (SHP-01).
"""

from decimal import Decimal

from mlb_baseball.model import pitch_movement


def _ensure_movement_tables(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_pitch')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.statcast_pitch ("
                "game_pk text, pitcher text, zone text, pitch_type text, "
                "pfx_z text, release_spin_rate text, type text, inning_topbot text, "
                "pitch_number text, _season text)"
            )
    db_conn.commit()


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_pitch')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.statcast_pitch")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.player")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_compute_matches_hand_calculation_and_gates_below_min_samples(db_conn):
    # G1: Home starter (1001) throws:
    #   10 FF @ pfx_z = 1.30 ft (= 15.60 in)
    #   10 CU @ pfx_z = -0.80 ft (= -9.60 in), spin = 2700 RPM
    # G1: Away batting sees:
    #   25 chase pitches with 10 swings (type='S') -> Chase% = 10/25 = 0.4000
    #   15 heart pitches with 12 swings (type='X') -> Heart Swing% = 12/15 = 0.8000
    # Entering G2:
    #   Fastball IVB = 15.60 in
    #   Curve Drop = -9.60 in
    #   Vert Separation = 15.60 - (-9.60) = 25.20 in
    #   Spin Rate = 2700 RPM
    #   Away Batting Chase% = 0.4000
    #   Away Batting Heart Swing% = 0.8000
    _reset(db_conn)
    _ensure_movement_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 9999, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 9999, 147) "
            "RETURNING id, retro_team_id"
        )
        teams = {retro_id: team_id for team_id, retro_id in cur.fetchall()}
        atl, nya = teams["ATL"], teams["NYA"]
        cur.execute(
            "INSERT INTO core.player (retro_id, mlbam_id, first_name, last_name) "
            "VALUES ('pitc001', '1001', 'Stephen', 'Strasburg'), "
            "('pitc002', '1002', 'Away', 'Pitcher') "
            "RETURNING id, mlbam_id"
        )
        players = {mlbam_id: player_id for player_id, mlbam_id in cur.fetchall()}
        p1, p2 = players["1001"], players["1002"]
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, game_pk, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', '7001', 2024, '2024-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', '7002', 2024, '2024-04-08', %(atl)s, %(nya)s, 4, 2, 'regular')",
            {"atl": atl, "nya": nya},
        )
        # Populate game features with starting pitchers
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(game_instance_key, mlb_game_pk, season, game_date, home_team_id, away_team_id, "
            "home_starter_id, away_starter_id, game_id) "
            "SELECT g.retro_game_id, g.game_pk::bigint, g.season, g.game_date, "
            "g.home_team_id, g.away_team_id, %(p1)s, %(p2)s, g.id FROM core.game g",
            {"p1": p1, "p2": p2},
        )
        pitches = []
        # 10 FF @ 1.30 ft
        for _ in range(10):
            pitches.append("('7001', '1001', '1', 'FF', '1.30', '2200', 'B', 'Top', '1', '2024')")
        # 10 CU @ -0.80 ft, 2700 rpm
        for _ in range(10):
            pitches.append("('7001', '1001', '14', 'CU', '-0.80', '2700', 'S', 'Top', '2', '2024')")

        # 15 additional chase pitches in Top half (Away batting) -> 10 previous + 15 = 25 total
        # 10 previous were swings (type='S'), next 15 are takes (type='B')
        for _ in range(15):
            pitches.append("('7001', '1001', '14', 'SL', '-0.50', '2500', 'B', 'Top', '3', '2024')")

        # 15 heart pitches in Top half (Away batting): 12 swings ('X'), 3 takes ('B')
        for _ in range(12):
            pitches.append("('7001', '1001', '5', 'FF', '1.30', '2200', 'X', 'Top', '4', '2024')")
        for _ in range(3):
            pitches.append("('7001', '1001', '5', 'FF', '1.30', '2200', 'B', 'Top', '5', '2024')")

        # G2 minimal row
        pitches.append("('7002', '1001', '5', 'FF', '1.30', '2200', 'B', 'Top', '1', '2024')")
        pitches.append("('7002', '1002', '5', 'FF', '1.20', '2100', 'B', 'Bot', '1', '2024')")

        cur.execute(
            "INSERT INTO raw.statcast_pitch "
            "(game_pk, pitcher, zone, pitch_type, pfx_z, release_spin_rate, type, "
            "inning_topbot, pitch_number, _season) "
            f"VALUES {', '.join(pitches)}"
        )
    db_conn.commit()

    updated = pitch_movement.compute(db_conn)
    db_conn.commit()

    assert updated >= 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_starter_fastball_ivb_in, f.home_starter_curve_drop_in, "
            "f.home_starter_vert_separation_in, f.home_starter_spin_rate_rpm, "
            "f.away_batting_chase_pct, f.away_batting_heart_swing_pct "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    assert rows["G1"] == (None, None, None, None, None, None)
    assert rows["G2"] == (
        Decimal("15.60"),
        Decimal("-7.44"),
        Decimal("23.04"),
        Decimal("2580"),
        Decimal("0.4000"),
        Decimal("0.8000"),
    )

    _reset(db_conn)


def test_compute_returns_zero_without_pitch_table(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.statcast_pitch")
    db_conn.commit()

    updated = pitch_movement.compute(db_conn)
    assert updated == 0
    _reset(db_conn)


def test_health_check_passes_on_clean_data(db_conn):
    _reset(db_conn)
    _ensure_movement_tables(db_conn)
    checks = pitch_movement.health_check()
    assert all(c.ok for c in checks)
    _reset(db_conn)
