"""Regression coverage for mlb_baseball.model.bullpen -- team-level
bullpen quality (rolling K%/BB%/FIP) and fatigue (trailing 3-day relief
outs) computed from raw.retrosheet_event (ADR-039).

Every value below is hand-computed and checked in the test itself, same
discipline as starter.py's tests.
"""

from decimal import Decimal

from mlb_baseball.model import bullpen, features


def _ensure_retrosheet_tables(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.retrosheet_event ("
                "game_id text, bat_home_id text, resp_pit_id text, "
                "resp_pit_start_fl text, bat_event_fl text, event_cd text, "
                "event_outs_ct text, _season text)"
            )
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        if not cur.fetchone()[0]:
            cur.execute("CREATE TABLE raw.retrosheet_gameinfo (gid text, gametype text)")
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


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.retrosheet_event")
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.retrosheet_gameinfo")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.player")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_compute_rolls_up_relief_only_with_zero_leakage_and_correct_fatigue_window(db_conn):
    # G1 (2020-04-01): ATL (home) starts startp1, who pitches 2 batters
    # faced (1 K, 1 generic out -- 2 outs, 0 BB/HR); ATL's reliever relp1
    # then faces 3 batters (1 BB, 1 HR, 1 generic out -- 1 out total, 0 K).
    # NYA (away) starts startp2 and pitches the whole game alone (1 generic
    # out, 1 BF) -- no NYA reliever appears in G1 at all.
    #
    # G2 (2020-04-03, 2 days later -- inside the 3-day fatigue window):
    # both teams again use only their starters (startp1, startp2), so
    # entering G2 we're checking values derived purely from G1's relief
    # activity, not from anything in G2 itself.
    #
    # Entering G2, ATL's rolling bullpen line is exactly relp1's G1 line:
    #   BF=3, K=0, BB=1, HBP=0, HR=1, outs=1
    #   k_pct = 0/3 = 0, bb_pct = 1/3 = 0.33333
    #   fip = (13*1 + 3*(1+0) - 2*0) / (1/3) + 3.10 = 16/0.33333 + 3.10 = 51.1
    #   fatigue (trailing 3 days before 2020-04-03, i.e. >= 03-31, < 04-03):
    #     G1 (04-01) qualifies -> relief outs = 1
    #
    # NYA never used a reliever in G1, so entering G2 its rolling bullpen
    # quality is NULL (zero relief appearances all season) and its
    # fatigue is 0 (the team_game backbone row for G1 exists with
    # zero-filled relief stats, so the trailing window sums to 0, not
    # NULL -- a real, present zero, not "no data").
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2020, '2020-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', 2020, '2020-04-03', %(atl)s, %(nya)s, 2, 1, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) "
            "VALUES ('G1', 'regular'), ('G2', 'regular')"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, bat_home_id, resp_pit_id, resp_pit_start_fl, "
            "bat_event_fl, event_cd, event_outs_ct, _season) VALUES "
            # ATL starter startp1 (bat_home_id='0' = pitching to the away team)
            "('G1', '0', 'startp1', 'T', 'T', '3', '1', '2020'), "  # K
            "('G1', '0', 'startp1', 'T', 'T', '2', '1', '2020'), "  # generic out
            # ATL reliever relp1, same team side, not the starter
            "('G1', '0', 'relp1', 'F', 'T', '14', '0', '2020'), "  # BB
            "('G1', '0', 'relp1', 'F', 'T', '23', '0', '2020'), "  # HR
            "('G1', '0', 'relp1', 'F', 'T', '2', '1', '2020'), "  # generic out
            # NYA starter startp2 (bat_home_id='1'), pitches the whole game alone
            "('G1', '1', 'startp2', 'T', 'T', '2', '1', '2020'), "
            # G2: both teams use only their starters again
            "('G2', '0', 'startp1', 'T', 'T', '2', '1', '2020'), "
            "('G2', '1', 'startp2', 'T', 'T', '2', '1', '2020')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = bullpen.compute(db_conn)
    db_conn.commit()

    assert updated == 2
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_bullpen_fip, f.home_bullpen_k_pct, "
            "f.home_bullpen_bb_pct, f.home_bullpen_fatigue, "
            "f.away_bullpen_fip, f.away_bullpen_k_pct, f.away_bullpen_bb_pct, "
            "f.away_bullpen_fatigue "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    # G1: nothing prior for either team -- everything NULL.
    g1 = rows["G1"]
    assert g1 == (None, None, None, None, None, None, None, None)

    # G2: ATL's rolling line derived purely from relp1's G1 appearance.
    g2 = rows["G2"]
    assert g2[0] == Decimal("51.1")
    assert g2[1] == Decimal("0")
    assert abs(g2[2] - Decimal("1") / Decimal("3")) < Decimal("0.0001")
    assert g2[3] == Decimal("1")  # fatigue: relp1's 1 out, within the 3-day window
    # NYA never used a reliever -- quality NULL, fatigue a real 0.
    assert g2[4] is None
    assert g2[5] is None
    assert g2[6] is None
    assert g2[7] == Decimal("0")

    _reset(db_conn)


def test_compute_gives_both_doubleheader_games_the_same_fatigue_value(db_conn):
    # ADR-042: fatigue is computed by collapsing to one row per
    # (team, calendar day) before the window RANGE frame, specifically
    # so two games sharing a date (a doubleheader) don't create peer-row
    # ambiguity. G1a/G1b are both on 2020-04-01 (ATL uses a reliever in
    # each); G2 (2020-04-03, within the 3-day window) must see the
    # SAME combined fatigue from both, not double-count or pick one
    # arbitrarily depending on row order.
    #   G1a relief outs = 1, G1b relief outs = 2 -> combined day total = 3
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type, game_number) VALUES "
            "('G1A', 2020, '2020-04-01', %(atl)s, %(nya)s, 5, 3, 'regular', 1), "
            "('G1B', 2020, '2020-04-01', %(atl)s, %(nya)s, 4, 2, 'regular', 2), "
            "('G2', 2020, '2020-04-03', %(atl)s, %(nya)s, 2, 1, 'regular', 0)",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) "
            "VALUES ('G1A', 'regular'), ('G1B', 'regular'), ('G2', 'regular')"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, bat_home_id, resp_pit_id, resp_pit_start_fl, "
            "bat_event_fl, event_cd, event_outs_ct, _season) VALUES "
            "('G1A', '0', 'startp1', 'T', 'T', '2', '1', '2020'), "
            "('G1A', '0', 'relp1', 'F', 'T', '2', '1', '2020'), "
            "('G1B', '0', 'startp1', 'T', 'T', '2', '1', '2020'), "
            "('G1B', '0', 'relp1', 'F', 'T', '2', '2', '2020'), "
            "('G1A', '1', 'startp2', 'T', 'T', '2', '1', '2020'), "
            "('G1B', '1', 'startp2', 'T', 'T', '2', '1', '2020'), "
            "('G2', '0', 'startp1', 'T', 'T', '2', '1', '2020'), "
            "('G2', '1', 'startp2', 'T', 'T', '2', '1', '2020')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    bullpen.compute(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT f.home_bullpen_fatigue FROM gold.game_feature f "
            "JOIN core.game g ON g.id = f.game_id WHERE g.retro_game_id = 'G2'"
        )
        (fatigue,) = cur.fetchone()
    assert fatigue == Decimal("3")

    _reset(db_conn)


def test_compute_returns_zero_without_retrosheet_event_table(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
    db_conn.commit()

    assert bullpen.compute(db_conn) == 0


def test_health_check_runs_cleanly_against_an_empty_database():
    checks = bullpen.health_check()
    assert len(checks) == 1
    assert all(c.name for c in checks)
