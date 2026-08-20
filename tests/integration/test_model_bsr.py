"""Regression coverage for mlb_baseball.model.bsr -- prior rolling team
stolen-base run value (wSB, ADR-083, admission queue BSR-01).
"""

from decimal import Decimal

import pytest

from mlb_baseball.model import bsr, features


def _reset(db_conn):
    # DROPs (not DELETEs) every stub table this file creates on demand --
    # see test_model_team_rate.py's identical _reset for the full
    # explanation (issue #7/#9 item 5).
    db_conn.rollback()
    with db_conn.cursor() as cur:
        for table in ("raw.retrosheet_event", "raw.retrosheet_gameinfo"):
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


@pytest.fixture(autouse=True)
def _clean(db_conn):
    _reset(db_conn)
    yield
    _reset(db_conn)


def _ensure_retrosheet_tables(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.retrosheet_event ("
                "game_id text, bat_home_id text, event_cd text, "
                "ab_fl text, sf_fl text, bat_event_fl text, _season text, "
                "run1_sb_fl text, run2_sb_fl text, run3_sb_fl text, "
                "run1_cs_fl text, run2_cs_fl text, run3_cs_fl text)"
            )
        else:
            cur.execute(
                "ALTER TABLE raw.retrosheet_event "
                "ADD COLUMN IF NOT EXISTS bat_event_fl text, "
                "ADD COLUMN IF NOT EXISTS run1_sb_fl text, "
                "ADD COLUMN IF NOT EXISTS run2_sb_fl text, "
                "ADD COLUMN IF NOT EXISTS run3_sb_fl text, "
                "ADD COLUMN IF NOT EXISTS run1_cs_fl text, "
                "ADD COLUMN IF NOT EXISTS run2_cs_fl text, "
                "ADD COLUMN IF NOT EXISTS run3_cs_fl text"
            )
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.retrosheet_gameinfo ("
                "gid text, gametype text, visteam text, hometeam text, _season text)"
            )
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


def test_compute_matches_hand_calculation_and_gates_below_min_attempts(db_conn):
    # ATL (home) entering G3: SB=3+2=5, CS=1+0=1 (sb+cs=6 >= MIN_ATTEMPTS=5
    # -- wsb computed). Opportunity (1B+UBB+HBP) = (4+2+1) + (4+2+1) = 14.
    # NYA (away) entering G3: SB=1+1=2, CS=0 (sb+cs=2 < MIN_ATTEMPTS=5 --
    # wsb gated to NULL despite a real, nonzero underlying value existing).
    #
    # League-wide entering context (both teams, G1+G2 combined):
    #   lg_sb = 5(ATL) + 2(NYA) = 7; lg_cs = 1(ATL) + 0(NYA) = 1
    #   lg_opp = (8+4+2)(ATL) + (4+2+0)(NYA) = 14 + 6 = 20
    #   lgwSB = (7*0.2 + 1*(-0.42)) / 20 = (1.4 - 0.42) / 20 = 0.049
    #
    # ATL wSB entering G3 = 5*0.2 + 1*(-0.42) - 0.049*14
    #                     = 1.0 - 0.42 - 0.686 = -0.106
    _ensure_retrosheet_tables(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2020, '2020-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', 2020, '2020-04-08', %(atl)s, %(nya)s, 4, 2, 'regular'), "
            "('G3', 2020, '2020-04-15', %(atl)s, %(nya)s, 6, 1, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) "
            "VALUES ('G1', 'regular'), ('G2', 'regular'), ('G3', 'regular')"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, bat_home_id, event_cd, ab_fl, sf_fl, bat_event_fl, _season, "
            "run1_sb_fl, run1_cs_fl) VALUES "
            # --- G1: ATL (home) ---
            "('G1', '1', '20', 'T', 'F', 'T', '2020', 'F', 'F'), "  # 1B (1/4)
            "('G1', '1', '20', 'T', 'F', 'T', '2020', 'F', 'F'), "  # 1B (2/4)
            "('G1', '1', '20', 'T', 'F', 'T', '2020', 'F', 'F'), "  # 1B (3/4)
            "('G1', '1', '20', 'T', 'F', 'T', '2020', 'F', 'F'), "  # 1B (4/4)
            "('G1', '1', '14', 'F', 'F', 'T', '2020', 'F', 'F'), "  # UBB (1/2)
            "('G1', '1', '14', 'F', 'F', 'T', '2020', 'F', 'F'), "  # UBB (2/2)
            "('G1', '1', '16', 'F', 'F', 'T', '2020', 'F', 'F'), "  # HBP
            "('G1', '1', '4',  'F', 'F', 'F', '2020', 'T', 'F'), "  # SB (1/3)
            "('G1', '1', '4',  'F', 'F', 'F', '2020', 'T', 'F'), "  # SB (2/3)
            "('G1', '1', '4',  'F', 'F', 'F', '2020', 'T', 'F'), "  # SB (3/3)
            "('G1', '1', '6',  'F', 'F', 'F', '2020', 'F', 'T'), "  # CS
            # --- G1: NYA (away) ---
            "('G1', '0', '20', 'T', 'F', 'T', '2020', 'F', 'F'), "  # 1B (1/2)
            "('G1', '0', '20', 'T', 'F', 'T', '2020', 'F', 'F'), "  # 1B (2/2)
            "('G1', '0', '14', 'F', 'F', 'T', '2020', 'F', 'F'), "  # UBB
            "('G1', '0', '4',  'F', 'F', 'F', '2020', 'T', 'F'), "  # SB
            # --- G2: ATL (home) ---
            "('G2', '1', '20', 'T', 'F', 'T', '2020', 'F', 'F'), "  # 1B (1/4)
            "('G2', '1', '20', 'T', 'F', 'T', '2020', 'F', 'F'), "  # 1B (2/4)
            "('G2', '1', '20', 'T', 'F', 'T', '2020', 'F', 'F'), "  # 1B (3/4)
            "('G2', '1', '20', 'T', 'F', 'T', '2020', 'F', 'F'), "  # 1B (4/4)
            "('G2', '1', '14', 'F', 'F', 'T', '2020', 'F', 'F'), "  # UBB (1/2)
            "('G2', '1', '14', 'F', 'F', 'T', '2020', 'F', 'F'), "  # UBB (2/2)
            "('G2', '1', '16', 'F', 'F', 'T', '2020', 'F', 'F'), "  # HBP
            "('G2', '1', '4',  'F', 'F', 'F', '2020', 'T', 'F'), "  # SB (1/2)
            "('G2', '1', '4',  'F', 'F', 'F', '2020', 'T', 'F'), "  # SB (2/2)
            # --- G2: NYA (away) ---
            "('G2', '0', '20', 'T', 'F', 'T', '2020', 'F', 'F'), "  # 1B (1/2)
            "('G2', '0', '20', 'T', 'F', 'T', '2020', 'F', 'F'), "  # 1B (2/2)
            "('G2', '0', '14', 'F', 'F', 'T', '2020', 'F', 'F'), "  # UBB
            "('G2', '0', '4',  'F', 'F', 'F', '2020', 'T', 'F'), "  # SB
            # --- G3: minimal rows so the window's current row exists ---
            "('G3', '1', '2', 'T', 'F', 'T', '2020', 'F', 'F'), "
            "('G3', '0', '2', 'T', 'F', 'T', '2020', 'F', 'F')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = bsr.compute(db_conn)
    db_conn.commit()

    assert updated == 3
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_sb, f.home_cs, f.home_wsb, "
            "f.away_sb, f.away_cs, f.away_wsb "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    assert rows["G1"] == (None, None, None, None, None, None)  # first game

    g3 = rows["G3"]
    assert g3[0] == 5  # home_sb (ungated)
    assert g3[1] == 1  # home_cs (ungated)
    expected_wsb = (
        Decimal("5") * Decimal("0.2")
        + Decimal("1") * Decimal("-0.42")
        - Decimal("0.049") * Decimal("14")
    )
    assert abs(g3[2] - expected_wsb) < Decimal("0.001")
    assert g3[3] == 2  # away_sb (ungated)
    assert g3[4] == 0  # away_cs (ungated)
    assert g3[5] is None  # away_wsb gated: sb+cs=2 < MIN_ATTEMPTS=5


def test_compute_returns_zero_without_retrosheet_event_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
    db_conn.commit()

    assert bsr.compute(db_conn) == 0


def test_compute_returns_zero_without_retrosheet_gameinfo_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_event ("
            "game_id text, bat_home_id text, event_cd text, "
            "ab_fl text, sf_fl text, bat_event_fl text, _season text, "
            "run1_sb_fl text, run2_sb_fl text, run3_sb_fl text, "
            "run1_cs_fl text, run2_cs_fl text, run3_cs_fl text)"
        )
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gameinfo")
    db_conn.commit()

    assert bsr.compute(db_conn) == 0


def test_health_check_flags_an_implausible_value(db_conn):
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
            "UPDATE gold.game_feature SET home_wsb = 999, home_sb = 10, home_cs = 2 "
            "WHERE game_id = (SELECT id FROM core.game WHERE retro_game_id = 'G1')"
        )
    db_conn.commit()

    checks = bsr.health_check()
    wsb_check = next(c for c in checks if c.name == "home_wsb plausible range")

    assert not wsb_check.ok
    assert "1 rows" in wsb_check.detail


def test_health_check_flags_a_min_sample_gate_violation(db_conn):
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
        # A populated home_wsb with sb+cs=1 (< MIN_ATTEMPTS=5) violates the
        # gate's own contract -- simulates the gate silently ceasing to
        # apply, which only a real-data check like this, not the fixture
        # test above, can catch.
        cur.execute(
            "UPDATE gold.game_feature SET home_wsb = -0.1, home_sb = 1, home_cs = 0 "
            "WHERE game_id = (SELECT id FROM core.game WHERE retro_game_id = 'G1')"
        )
    db_conn.commit()

    checks = bsr.health_check()
    gate_check = next(c for c in checks if c.name == "home_wsb min-sample gate holds")

    assert not gate_check.ok
    assert "1 rows" in gate_check.detail


def test_health_check_flags_a_coverage_gap(db_conn):
    _ensure_retrosheet_tables(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2020, '2020-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', 2020, '2020-04-08', %(atl)s, %(nya)s, 2, 1, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) "
            "VALUES ('G1', 'regular'), ('G2', 'regular')"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, bat_home_id, event_cd, ab_fl, sf_fl, bat_event_fl, _season) VALUES "
            "('G1', '1', '20', 'T', 'F', 'T', '2020'), "
            "('G1', '0', '2', 'T', 'F', 'T', '2020'), "
            "('G2', '1', '2', 'T', 'F', 'T', '2020'), "
            "('G2', '0', '2', 'T', 'F', 'T', '2020')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    bsr.compute(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT f.home_sb FROM gold.game_feature f "
            "JOIN core.game g ON g.id = f.game_id WHERE g.retro_game_id = 'G2'"
        )
        (sb,) = cur.fetchone()
    assert sb is not None  # sanity: compute() really did populate it

    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE gold.game_feature SET home_sb = NULL "
            "WHERE game_id = (SELECT id FROM core.game WHERE retro_game_id = 'G2')"
        )
    db_conn.commit()

    checks = bsr.health_check()
    coverage_check = next(c for c in checks if c.name == "home_sb coverage")

    assert not coverage_check.ok
    assert "1 eligible rows" in coverage_check.detail
