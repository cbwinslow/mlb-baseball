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


def test_compute_counts_foul_tips_and_hit_batters_per_verified_csw_formula(db_conn):
    """ADR-263 regression: CSW% must include foul tips (Retrosheet code `T`)
    in its numerator, and total pitches (`Total Pitches`, the denominator of
    CSW% and every other rate here) must include hit-by-pitch (`H`).

    Both are directly checkable against real, cited external sources:
    - Retrosheet's own event-file spec (retrosheet.org/eventfile.htm,
      "pitches" field) documents `H` (hit batter) as a real pitch code --
      the pitcher actually threw a ball, it just hit the batter -- so it
      must count toward "Total Pitches". The pre-fix code's whitelist
      (`[^BCFKLMOPSTUVWXI]`) omitted `H` entirely (and included a `W` that
      is not a real Retrosheet code at all).
    - Pitcher List's original CSW definition ("CSW Rate: An Intro to an
      Important New Metric", the article that coined the term in 2018)
      states explicitly that CSW counts "called strikes, swinging strikes
      (including blocked ones), swinging pitchouts and foul tips into the
      glove" -- i.e. foul tips (`T`) belong in the numerator. The pre-fix
      code's CSW keep-set (`[^CSM]`) omitted `T` entirely, undercounting
      CSW for every pitcher who ever recorded a foul tip.
    """
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
        # G1: foult001 (home starter) pitches 7 PAs = 22 real pitches:
        # PA1 'CTX'  : C=called strike, T=foul tip, X=in play.
        #              CSW=C,T=2  Whiff=0  Swings=T,X=2  FStrike=1 (C)
        # PA2 'BBH'  : B,B=balls, H=hit batter (ends PA; a real thrown pitch).
        #              CSW=0      Whiff=0  Swings=0        FStrike=0 (B)
        # PA3 'SSS'  : three swinging strikes (K swinging).
        #              CSW=3      Whiff=3  Swings=3        FStrike=1 (S)
        # PA4 'CCC'  : three called strikes (K looking).
        #              CSW=3      Whiff=0  Swings=0        FStrike=1 (C)
        # PA5 'FFX'  : F,F=fouls (excluded from CSW, still swings), X=in play.
        #              CSW=0      Whiff=0  Swings=F,F,X=3  FStrike=1 (F)
        # PA6 'BBBB' : four balls (walk).
        #              CSW=0      Whiff=0  Swings=0        FStrike=0 (B)
        # PA7 'SSB'  : two swinging strikes then a ball.
        #              CSW=2      Whiff=2  Swings=S,S=2    FStrike=1 (S)
        # Totals: Pitches=3+3+3+3+3+4+3=22, CSW=2+0+3+3+0+0+2=10,
        #         Whiffs=0+0+3+0+0+0+2=5, Swings=2+0+3+0+3+0+2=10,
        #         FStrikes=1+0+1+1+1+0+1=5, PA=7
        # Expected: CSW% = 10/22 = 0.45454..., Whiff% = 5/10 = 0.5,
        #           FStrike% = 5/7 = 0.71428...
        #
        # Pre-fix (buggy) formula for comparison, proving this is a real
        # behavior change and not just a no-op: pitch_count excluded `H`
        # (PA2 -> 2 pitches, not 3) and csw_count excluded `T` (PA1 -> CSW=1,
        # not 2), giving Pitches=21, CSW=9, CSW%=9/21=0.42857... -- a
        # different, wrong answer.
        events = [
            ("G1", "0", "foult001", "T", "T", "CTX"),
            ("G1", "0", "foult001", "T", "T", "BBH"),
            ("G1", "0", "foult001", "T", "T", "SSS"),
            ("G1", "0", "foult001", "T", "T", "CCC"),
            ("G1", "0", "foult001", "T", "T", "FFX"),
            ("G1", "0", "foult001", "T", "T", "BBBB"),
            ("G1", "0", "foult001", "T", "T", "SSB"),
            # G2 events (irrelevant filler so degrj-style starter resolution works)
            ("G2", "0", "foult001", "T", "T", "BBB"),
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

    # Entering G2, foult001 has G1's corrected stats.
    assert abs(res["G2"][0] - Decimal("0.45454545454545454545")) < Decimal("0.0001")  # 10 / 22
    assert res["G2"][1] == Decimal("0.5")  # 5 / 10
    assert abs(res["G2"][2] - Decimal("0.71428571428571428571")) < Decimal("0.0001")  # 5 / 7

    # And explicitly not the pre-fix (wrong) value -- a real regression guard.
    assert abs(res["G2"][0] - Decimal("0.42857142857142857143")) > Decimal("0.001")


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
