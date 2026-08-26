"""Integration tests for Platoon Splits & Handedness Matchups (PLT-01, ADR-101)."""

from mlb_baseball.model import platoon


def _ensure_tables(db_conn):
    # DROP + unconditional CREATE, not an "IF NOT EXISTS" guard: several
    # other test files (test_model_command.py, test_model_pitch_movement.py,
    # test_conform.py, test_audit_db.py) also create raw.statcast_pitch,
    # each with its own different column set for its own needs, and the
    # underlying test database template persists mutations across separate
    # pytest invocations -- see test_model_command.py's identical guard for
    # the confirmed failure mode.
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.statcast_pitch")
        cur.execute(
            "CREATE TABLE raw.statcast_pitch ("
            "game_date text, home_team text, away_team text, "
            "pitcher text, p_throws text, woba_value text, woba_denom text)"
        )
    db_conn.commit()


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.player WHERE id IN (101, 102)")
        # core.game must go before core.team: this repo's test database is
        # one shared, session-scoped instance, so a real leftover
        # core.game row from an earlier test can reference a team this
        # DELETE would otherwise try to remove, violating
        # game_home_team_id_fkey/game_away_team_id_fkey -- confirmed
        # directly (a real FK violation once the full suite could finally
        # run start to finish, not a mock/assumption).
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
        cur.execute("SELECT to_regclass('raw.statcast_pitch')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.statcast_pitch")
    db_conn.commit()


def _seed_teams(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('BOS', 'Boston', 'Red Sox', 1901, 2025, 111), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147) "
            "RETURNING id, retro_team_id"
        )
        return {retro_id: team_id for team_id, retro_id in cur.fetchall()}


def test_platoon_splits_hand_calculated_math(db_conn):
    _ensure_tables(db_conn)
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    bos_id = teams["BOS"]
    nya_id = teams["NYA"]

    with db_conn.cursor() as cur:
        # Home Starter (id 101): Left-handed ('L')
        # Away Starter (id 102): Right-handed ('R')
        cur.execute(
            "INSERT INTO core.player (id, retro_id, mlbam_id, first_name, last_name) VALUES "
            "(101, 'p1_retro', '101', 'Chris', 'Sale'), "
            "(102, 'p2_retro', '102', 'Gerrit', 'Cole') "
            "ON CONFLICT (id) DO NOTHING"
        )
        cur.execute(
            "INSERT INTO raw.statcast_pitch (pitcher, p_throws) VALUES ('101', 'L'), ('102', 'R')"
        )

        # Game G1:
        # Home wOBA = 0.350, Away Starter (P2) vs RHB wOBA allowed = 0.310
        # Away wOBA = 0.330, Home Starter (P1) vs LHB wOBA allowed = 0.280
        cur.execute(
            "INSERT INTO gold.game_feature ("
            "game_instance_key, season, game_date, home_team_id, away_team_id, "
            "home_starter_id, away_starter_id, home_woba, away_woba, "
            "home_starter_vs_lhb_woba, home_starter_vs_rhb_woba, "
            "away_starter_vs_lhb_woba, away_starter_vs_rhb_woba) VALUES ("
            "'G1', 2024, '2024-05-01', %(home_id)s, %(away_id)s, "
            "101, 102, 0.350, 0.330, 0.280, 0.340, 0.360, 0.310)",
            {"home_id": bos_id, "away_id": nya_id},
        )
    db_conn.commit()

    rows = platoon.compute(db_conn)
    assert rows >= 1

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_starter_throws, away_starter_throws, "
            "home_platoon_matchup_woba_diff, away_platoon_matchup_woba_diff "
            "FROM gold.game_feature WHERE game_instance_key = 'G1'"
        )
        row = cur.fetchone()
        assert row is not None
        h_throws, a_throws, h_diff, a_diff = row

        assert h_throws == "L"
        assert a_throws == "R"
        # Away starter throws R: Home diff = 0.350 - 0.310 = +0.040
        assert abs(float(h_diff) - 0.040) < 1e-4
        # Home starter throws L: Away diff = 0.330 - 0.280 = +0.050
        assert abs(float(a_diff) - 0.050) < 1e-4

    _reset(db_conn)


def test_platoon_health_check_bounds(db_conn):
    _ensure_tables(db_conn)
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    bos_id = teams["BOS"]
    nya_id = teams["NYA"]

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gold.game_feature ("
            "game_instance_key, season, game_date, home_team_id, away_team_id, "
            "home_starter_throws, away_starter_throws, "
            "home_platoon_matchup_woba_diff, away_platoon_matchup_woba_diff) VALUES "
            "('G1', 2024, '2024-05-01', %(home_id)s, %(away_id)s, 'L', 'R', 0.050, -0.020)",
            {"home_id": bos_id, "away_id": nya_id},
        )
    db_conn.commit()

    checks = platoon.health_check()
    assert all(c.ok for c in checks)
    _reset(db_conn)
