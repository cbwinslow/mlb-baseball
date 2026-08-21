"""Regression coverage for mlb_baseball.model.pitch_discipline -- plate discipline
and pitch sequence rates (PIT-07, ADR-089).
"""

from decimal import Decimal

import pytest

from mlb_baseball.model import features, pitch_discipline


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        for table in ("raw.retrosheet_event", "raw.retrosheet_gameinfo", "raw.mlb_schedule"):
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
                "game_id text, bat_home_id text, resp_pit_id text, "
                "resp_pit_start_fl text, bat_event_fl text, pitch_seq_tx text, "
                "_season text)"
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
        teams = {retro_id: team_id for team_id, retro_id in cur.fetchall()}
    db_conn.commit()
    return teams


def test_compute_calculates_pitch_discipline_with_zero_leakage(db_conn):
    _ensure_retrosheet_tables(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2024, '2024-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', 2024, '2024-04-05', %(atl)s, %(nya)s, 4, 2, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) "
            "VALUES ('G1', 'regular'), ('G2', 'regular')"
        )
        # G1: degrj001 (home starter, bat_home_id='0') pitches 20 total pitches across 6 PAs:
        # PA1: 'CBX' (3 pitches: 1 C, 0 S, 1 X; Swings=1, FStrike=1)
        # PA2: 'SSB' (3 pitches: 0 C, 2 S, 0 X; Swings=2, FStrike=1)
        # PA3: 'BFFX' (4 pitches: 0 C, 0 S, 2 F, 1 X; Swings=3, FStrike=0)
        # PA4: 'CCC' (3 pitches: 3 C, 0 S, 0 X; Swings=0, FStrike=1)
        # PA5: 'FSBB' (4 pitches: 0 C, 1 S, 1 F; Swings=2, FStrike=1)
        # PA6: 'SMS' (3 pitches: 0 C, 3 Whiffs (2S, 1M); Swings=3, FStrike=1)
        # Totals: Pitches = 20, CSW = 10, Whiffs = 6, Swings = 11, FStrikes = 5, PA = 6
        # Expected: CSW% = 10/20 = 0.500, Whiff% = 6/11 = 0.54545..., FStrike% = 5/6 = 0.8333...
        events = [
            ("G1", "0", "degrj001", "T", "T", "CBX"),
            ("G1", "0", "degrj001", "T", "T", "SSB"),
            ("G1", "0", "degrj001", "T", "T", "BFFX"),
            ("G1", "0", "degrj001", "T", "T", "CCC"),
            ("G1", "0", "degrj001", "T", "T", "FSBB"),
            ("G1", "0", "degrj001", "T", "T", "SMS"),
            # G2 events
            ("G2", "0", "degrj001", "T", "T", "BBB"),
            ("G2", "1", "cole0001", "T", "T", "BBB"),
        ]
        cur.executemany(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, bat_home_id, resp_pit_id, resp_pit_start_fl, bat_event_fl, pitch_seq_tx) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            events,
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    rows_updated = pitch_discipline.compute(db_conn)
    db_conn.commit()
    assert rows_updated > 0

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_starter_csw_pct, "
            "f.home_starter_whiff_pct, f.home_starter_fstrike_pct "
            "FROM gold.game_feature f "
            "JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.game_date"
        )
        res = {row[0]: (row[1], row[2], row[3]) for row in cur.fetchall()}

    # G1: Entering G1, degrj001 has no prior games -> NULL
    assert res["G1"][0] is None
    assert res["G1"][1] is None
    assert res["G1"][2] is None

    # G2: Entering G2, degrj001 has G1's stats
    assert res["G2"][0] == Decimal("0.5")  # 10 / 20
    assert abs(res["G2"][1] - Decimal("0.54545454545454545455")) < Decimal("0.001")  # 6 / 11
    assert abs(res["G2"][2] - Decimal("0.83333333333333333333")) < Decimal("0.001")  # 5 / 6


def test_compute_is_idempotent(db_conn):
    _ensure_retrosheet_tables(db_conn)
    teams = _seed_teams(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2024, '2024-04-01', %(atl)s, %(nya)s, 5, 3, 'regular')",
            {"atl": teams["ATL"], "nya": teams["NYA"]},
        )
        cur.execute("INSERT INTO raw.retrosheet_gameinfo (gid, gametype) VALUES ('G1', 'regular')")
    db_conn.commit()
    features.build(db_conn)
    db_conn.commit()
    first = pitch_discipline.compute(db_conn)
    db_conn.commit()
    second = pitch_discipline.compute(db_conn)
    db_conn.commit()
    assert first == second


def test_compute_missing_table_gate(db_conn):
    # Without retrosheet tables, compute() returns 0
    assert pitch_discipline.compute(db_conn) == 0


def test_health_check_passes(db_conn):
    checks = pitch_discipline.health_check()
    assert all(c.ok for c in checks)
