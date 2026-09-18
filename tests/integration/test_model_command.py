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


def test_compute_does_not_double_count_first_pitch_shadow_zone_as_heart(db_conn):
    """Regression for a real bug: heart_pitches used to also count any
    first-pitch-of-PA (pitch_number = 1) landing in the Shadow zone as
    Heart, on top of it already counting toward shadow_pitches -- double
    counted, with no basis in the cited formula (Heart% = zone 5 pitches
    only). Every pitch here uses zone/pitch_number combinations the old
    bug mishandled; the fix requires heart_pct + shadow_pct + chase_pct
    to sum to exactly 1.0 (every pitch counted in exactly one bucket),
    which the old code violated (it summed to 1.5 for this fixture).
    """
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
            "VALUES ('pitc003', '1003', 'Bug', 'Reproducer'), "
            "('pitc004', '1004', 'Away', 'Pitcher') "
            "RETURNING id, mlbam_id"
        )
        players = {mlbam_id: player_id for player_id, mlbam_id in cur.fetchall()}
        p1, p2 = players["1003"], players["1004"]
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, game_pk, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', '7101', 2024, '2024-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', '7102', 2024, '2024-04-08', %(atl)s, %(nya)s, 4, 2, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(game_instance_key, mlb_game_pk, season, game_date, home_team_id, away_team_id, "
            "home_starter_id, away_starter_id, game_id) "
            "SELECT g.retro_game_id, g.game_pk::bigint, g.season, g.game_date, "
            "g.home_team_id, g.away_team_id, %(p1)s, %(p2)s, g.id FROM core.game g",
            {"p1": p1, "p2": p2},
        )
        pitches = []
        # 5 unambiguous heart pitches (zone 5, first pitch of the PA --
        # correctly Heart regardless of pitch_number).
        for _ in range(5):
            pitches.append("('7101', '1003', '5', 'FF', '95.0', 'Top', '1', '2024')")
        # 10 Shadow-zone pitches, all first-pitch-of-PA -- the exact case
        # the bug mis-scored as Heart on top of Shadow.
        for _ in range(10):
            pitches.append("('7101', '1003', '1', 'FF', '95.0', 'Top', '1', '2024')")
        # 5 Chase-zone pitches, first pitch of the PA (unaffected by the
        # bug either way -- included to prove chase_pct is undisturbed).
        for _ in range(5):
            pitches.append("('7101', '1003', '11', 'SL', '84.0', 'Top', '1', '2024')")

        # G2 minimal row so the rolling window has somewhere to land.
        pitches.append("('7102', '1003', '5', 'FF', '95.0', 'Top', '2', '2024')")
        pitches.append("('7102', '1004', '5', 'FF', '94.0', 'Bot', '2', '2024')")

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
            "f.home_starter_chase_pct "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    heart_pct, shadow_pct, chase_pct = rows["G2"]
    # Not the old buggy 0.7500 (5 zone-5 + 10 double-counted shadow-as-heart).
    assert heart_pct == Decimal("0.2500")
    assert shadow_pct == Decimal("0.5000")
    assert chase_pct == Decimal("0.2500")
    # Every pitch counted in exactly one bucket -- the old bug summed to 1.5.
    assert heart_pct + shadow_pct + chase_pct == Decimal("1.0000")

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
