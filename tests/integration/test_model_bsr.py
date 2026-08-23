"""Regression coverage for mlb_baseball.model.bsr -- prior rolling team
baserunning metrics (wSB, XBT%, UBR, wGDP, and BsR Total, RUN-01).
"""

from decimal import Decimal

import pytest

from mlb_baseball.model import bsr, features


def _reset(db_conn):
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
                "run1_cs_fl text, run2_cs_fl text, run3_cs_fl text, "
                "gdp_fl text, run1_dest_id text, run2_dest_id text, "
                "base1_run_id text, base2_run_id text)"
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
                "ADD COLUMN IF NOT EXISTS run3_cs_fl text, "
                "ADD COLUMN IF NOT EXISTS gdp_fl text, "
                "ADD COLUMN IF NOT EXISTS run1_dest_id text, "
                "ADD COLUMN IF NOT EXISTS run2_dest_id text, "
                "ADD COLUMN IF NOT EXISTS base1_run_id text, "
                "ADD COLUMN IF NOT EXISTS base2_run_id text"
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
            "run1_sb_fl, run1_cs_fl, gdp_fl, run1_dest_id, base1_run_id) VALUES "
            # --- G1: ATL (home) ---
            "('G1', '1', '20', 'T', 'F', 'T', '2020', 'F', 'F', 'F', '3', 'p1'), "  # 1B + XBT
            "('G1', '1', '20', 'T', 'F', 'T', '2020', 'F', 'F', 'F', '2', 'p2'), "  # 1B
            "('G1', '1', '20', 'T', 'F', 'T', '2020', 'F', 'F', 'F', '3', 'p3'), "  # 1B + XBT
            "('G1', '1', '20', 'T', 'F', 'T', '2020', 'F', 'F', 'F', '2', 'p4'), "  # 1B
            "('G1', '1', '14', 'F', 'F', 'T', '2020', 'F', 'F', 'F', '0', ''), "  # UBB (1/2)
            "('G1', '1', '14', 'F', 'F', 'T', '2020', 'F', 'F', 'F', '0', ''), "  # UBB (2/2)
            "('G1', '1', '16', 'F', 'F', 'T', '2020', 'F', 'F', 'F', '0', ''), "  # HBP
            "('G1', '1', '4',  'F', 'F', 'F', '2020', 'T', 'F', 'F', '0', ''), "  # SB (1/3)
            "('G1', '1', '4',  'F', 'F', 'F', '2020', 'T', 'F', 'F', '0', ''), "  # SB (2/3)
            "('G1', '1', '4',  'F', 'F', 'F', '2020', 'T', 'F', 'F', '0', ''), "  # SB (3/3)
            "('G1', '1', '6',  'F', 'F', 'F', '2020', 'F', 'T', 'F', '0', ''), "  # CS
            # --- G1: NYA (away) ---
            "('G1', '0', '20', 'T', 'F', 'T', '2020', 'F', 'F', 'F', '0', ''), "  # 1B (1/2)
            "('G1', '0', '20', 'T', 'F', 'T', '2020', 'F', 'F', 'F', '0', ''), "  # 1B (2/2)
            "('G1', '0', '14', 'F', 'F', 'T', '2020', 'F', 'F', 'F', '0', ''), "  # UBB
            "('G1', '0', '4',  'F', 'F', 'F', '2020', 'T', 'F', 'F', '0', ''), "  # SB
            # --- G2: ATL (home) ---
            "('G2', '1', '20', 'T', 'F', 'T', '2020', 'F', 'F', 'F', '3', 'p1'), "  # 1B + XBT
            "('G2', '1', '20', 'T', 'F', 'T', '2020', 'F', 'F', 'F', '2', 'p2'), "  # 1B
            "('G2', '1', '20', 'T', 'F', 'T', '2020', 'F', 'F', 'F', '3', 'p3'), "  # 1B + XBT
            "('G2', '1', '20', 'T', 'F', 'T', '2020', 'F', 'F', 'F', '2', 'p4'), "  # 1B
            "('G2', '1', '14', 'F', 'F', 'T', '2020', 'F', 'F', 'F', '0', ''), "  # UBB (1/2)
            "('G2', '1', '14', 'F', 'F', 'T', '2020', 'F', 'F', 'F', '0', ''), "  # UBB (2/2)
            "('G2', '1', '16', 'F', 'F', 'T', '2020', 'F', 'F', 'F', '0', ''), "  # HBP
            "('G2', '1', '4',  'F', 'F', 'F', '2020', 'T', 'F', 'F', '0', ''), "  # SB (1/2)
            "('G2', '1', '4',  'F', 'F', 'F', '2020', 'T', 'F', 'F', '0', ''), "  # SB (2/2)
            # --- G2: NYA (away) ---
            "('G2', '0', '20', 'T', 'F', 'T', '2020', 'F', 'F', 'F', '0', ''), "  # 1B (1/2)
            "('G2', '0', '20', 'T', 'F', 'T', '2020', 'F', 'F', 'F', '0', ''), "  # 1B (2/2)
            "('G2', '0', '14', 'F', 'F', 'T', '2020', 'F', 'F', 'F', '0', ''), "  # UBB
            "('G2', '0', '4',  'F', 'F', 'F', '2020', 'T', 'F', 'F', '0', ''), "  # SB
            # --- G3: minimal rows so the window's current row exists ---
            "('G3', '1', '2', 'T', 'F', 'T', '2020', 'F', 'F', 'F', '0', ''), "
            "('G3', '0', '2', 'T', 'F', 'T', '2020', 'F', 'F', 'F', '0', '')"
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
            "f.away_sb, f.away_cs, f.away_wsb, f.home_xbt_pct, f.home_ubr_runs, f.home_bsr_total "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    assert rows["G1"] == (None, None, None, None, None, None, None, None, None)  # first game

    g3 = rows["G3"]
    assert g3[0] == 5  # home_sb (ungated)
    assert g3[1] == 1  # home_cs (ungated)
    assert g3[2] is not None  # home_wsb
    assert g3[3] == 2  # away_sb (ungated)
    assert g3[4] == 0  # away_cs (ungated)
    assert g3[5] is None  # away_wsb gated: sb+cs=2 < MIN_ATTEMPTS=5
    assert g3[6] == Decimal("0.5000")  # 4 extra bases / 8 opportunities = 0.5000
    assert g3[7] is not None  # ubr_runs
    assert g3[8] is not None  # bsr_total


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
            "UPDATE gold.game_feature SET home_wsb = 999 "
            "WHERE game_id = (SELECT id FROM core.game WHERE retro_game_id = 'G1')"
        )
    db_conn.commit()

    checks = bsr.health_check()
    domain_check = next(c for c in checks if c.name == "model.bsr_comprehensive.domain")

    assert not domain_check.ok
    assert "outside valid domain bounds" in domain_check.detail
