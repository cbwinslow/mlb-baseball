"""Regression coverage for mlb_baseball.model.command -- strike zone command,
attack zones (Heart, Shadow, Chase), and pitch velocity deltas (COM-01).
"""

from decimal import Decimal

from mlb_baseball.model import command


def _ensure_command_tables(db_conn):
    # DROP + unconditional CREATE, not an "IF NOT EXISTS" guard: several
    # other test files (test_model_platoon.py, test_model_pitch_movement.py,
    # test_conform.py, test_audit_db.py) also create raw.statcast_pitch,
    # each with its own different column set for its own needs, and the
    # underlying test database template persists mutations across separate
    # pytest invocations -- confirmed directly: this file's own INSERT
    # failed against a stale schema left over from a different file's run,
    # even with this file's guard running first in that invocation.
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.statcast_pitch")
        cur.execute(
            "CREATE TABLE raw.statcast_pitch ("
            "game_pk text, pitcher text, zone text, pitch_type text, "
            "release_speed text, inning_topbot text, pitch_number text, _season text)"
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
    # G1: Home starter (1001) throws 25 pitches:
    #   5 in zone 5 (Heart) -> Heart = 5
    #   10 in zones 1-9 (Shadow) -> Shadow = 10
    #   10 in zones 11-14 (Chase) -> Chase = 10
    #   10 FF @ 95.0 mph, 5 CH @ 85.0 mph -> Velo delta = 10.00 mph
    # Entering G2:
    #   Heart% = 5/25 = 0.2000
    #   Shadow% = 10/25 = 0.4000
    #   Chase% = 10/25 = 0.4000
    #   Fastball velo = 95.00
    #   Velo delta = 10.00
    _reset(db_conn)
    _ensure_command_tables(db_conn)
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
            "VALUES ('pitc001', '1001', 'Ace', 'Pitcher'), "
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
        # 25 pitches in G1 for 1001
        pitches = []
        # 5 heart pitches
        for _ in range(5):
            pitches.append("('7001', '1001', '5', 'FF', '95.0', 'Top', '2', '2024')")
        # 10 shadow pitches (5 FF @ 95.0, 5 CH @ 85.0)
        for _ in range(5):
            pitches.append("('7001', '1001', '1', 'FF', '95.0', 'Top', '2', '2024')")
        for _ in range(5):
            pitches.append("('7001', '1001', '2', 'CH', '85.0', 'Top', '2', '2024')")
        # 10 chase pitches
        for _ in range(10):
            pitches.append("('7001', '1001', '14', 'SL', '84.0', 'Top', '2', '2024')")

        # G2 minimal row
        pitches.append("('7002', '1001', '5', 'FF', '95.0', 'Top', '2', '2024')")
        pitches.append("('7002', '1002', '5', 'FF', '94.0', 'Bot', '2', '2024')")

        cur.execute(
            "INSERT INTO raw.statcast_pitch "
            "(game_pk, pitcher, zone, pitch_type, release_speed, inning_topbot, "
            "pitch_number, _season) "
            f"VALUES {', '.join(pitches)}"
        )
    db_conn.commit()

    updated = command.compute(db_conn)
    db_conn.commit()

    assert updated >= 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_starter_heart_pct, f.home_starter_shadow_pct, "
            "f.home_starter_chase_pct, f.home_starter_fastball_velo, f.home_starter_velo_delta "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    assert rows["G1"] == (None, None, None, None, None)
    assert rows["G2"] == (
        Decimal("0.2000"),
        Decimal("0.4000"),
        Decimal("0.4000"),
        Decimal("95.00"),
        Decimal("10.67"),
    )

    _reset(db_conn)


def test_compute_returns_zero_without_pitch_table(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.statcast_pitch")
    db_conn.commit()

    updated = command.compute(db_conn)
    assert updated == 0
    _reset(db_conn)


def test_health_check_passes_on_clean_data(db_conn):
    _reset(db_conn)
    _ensure_command_tables(db_conn)
    checks = command.health_check()
    assert all(c.ok for c in checks)
    _reset(db_conn)
