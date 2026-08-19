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
        else:
            for column in (
                "game_id",
                "bat_home_id",
                "resp_pit_id",
                "resp_pit_start_fl",
                "bat_event_fl",
                "event_cd",
                "event_outs_ct",
                "_season",
            ):
                cur.execute(
                    f"ALTER TABLE raw.retrosheet_event ADD COLUMN IF NOT EXISTS {column} text"
                )
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.retrosheet_gameinfo ("
                "gid text, gametype text, visteam text, hometeam text, _season text)"
            )
        else:
            cur.execute(
                "ALTER TABLE raw.retrosheet_gameinfo "
                "ADD COLUMN IF NOT EXISTS visteam text, "
                "ADD COLUMN IF NOT EXISTS hometeam text, "
                "ADD COLUMN IF NOT EXISTS _season text"
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


def _reset(db_conn):
    # DROPs (not DELETEs) every stub table this file creates on demand --
    # see test_model_offense.py's identical _reset for the full explanation
    # (issue #7): each test_model_*.py file creates its own minimal schema
    # for these tables, and a stale stub from an earlier file's run breaks
    # later files' schema expectations. All four tables here are created
    # ad-hoc by this file's own fixtures, never by a migration, so dropping
    # them is always safe -- this also replaces the old single
    # last-test-in-this-file cleanup (order-dependent, fragile) with a
    # per-test drop that works regardless of collection order.
    db_conn.rollback()
    with db_conn.cursor() as cur:
        for table in (
            "raw.retrosheet_event",
            "raw.retrosheet_gameinfo",
            "raw.mlb_schedule",
            "raw.mlb_playbyplay",
        ):
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.player")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def _ensure_playbyplay_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_playbyplay')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.mlb_playbyplay ("
                "game_pk text, at_bat_index text, inning text, half_inning text, "
                "pitcher_id text, event_type text, outs text, _season text)"
            )
    db_conn.commit()


def _ensure_mlb_schedule_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.mlb_schedule ("
                "game_id text, _season text, game_date text, game_type text, "
                "status text, home_id text, away_id text, game_num text, "
                "venue_id text)"
            )
    db_conn.commit()


def _seed_teams_2026(db_conn):
    # Same shape as _seed_teams, but with last_year extended to 2026 --
    # features.py's own upcoming-games union requires
    # `season BETWEEN first_year AND last_year` (see its own docstring),
    # so a 2026 raw.mlb_schedule row needs the team's range to cover it.
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 2026, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 2026, 147) "
            "RETURNING id, retro_team_id"
        )
        return {retro_id: team_id for team_id, retro_id in cur.fetchall()}


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


def test_compute_orders_quality_window_by_game_number_not_insertion_order(db_conn):
    # Issue #9 item 6 (found by direct audit, same bug class as item 1's
    # db97d96 fix for team_rate_retrosheet_update.sql): the rolling QUALITY
    # window (k_pct/bb_pct/fip) used to order same-date rows by `game_id`
    # (an insertion-order serial), not the declared `game_number`. The
    # fatigue window is deliberately immune to this (collapsed to one row
    # per team-day first, see test_compute_gives_both_doubleheader_games_
    # the_same_fatigue_value and the module docstring) -- this test targets
    # the separate quality window specifically.
    #
    # DH2 (game_number=2) is inserted BEFORE DH1 (game_number=1) so DH2
    # gets the LOWER core.game.id despite being the chronologically later
    # game -- this is what would fool an insertion-order sort.
    #   G1 (2020-04-01): ATL reliever relp1 faces 2 batters (1 K, 1 out).
    #   DH1 (game_number=1): ATL reliever relp1 faces 1 batter (1 BB).
    #   DH2 (game_number=2): ATL reliever relp1 faces 1 batter (1 out) --
    #     only needs a row so the window has a "current row".
    # Correctly ordered by game_number, entering DH2 pools G1 + DH1 relief:
    #   k_sum=1, bb_sum=1, bf_sum=3, hr_sum=0, outs_sum=2
    #   k_pct = 1/3 = 0.33333, bb_pct = 1/3 = 0.33333
    #   fip = (13*0 + 3*(1+0) - 2*1) / (2/3) + 3.10 = 1/0.66667 + 3.10 = 4.60
    # If ordered by insertion order instead (the bug), DH2 (lower game_id)
    # would sort before DH1, so entering DH2 would only see G1's relief:
    #   k_pct = 1/2 = 0.5, bb_pct = 0, fip = -2/0.66667 + 3.10 = 0.10
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, game_number, home_team_id, "
            "away_team_id, home_score, away_score, game_type) VALUES "
            "('G1', 2020, '2020-04-01', 1, %(atl)s, %(nya)s, 5, 3, 'regular')",
            {"atl": atl, "nya": nya},
        )
        # DH2 (game_number=2) inserted before DH1 (game_number=1) on
        # purpose -- this is what gives DH2 the lower serial game_id.
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, game_number, home_team_id, "
            "away_team_id, home_score, away_score, game_type) VALUES "
            "('DH2', 2020, '2020-04-08', 2, %(atl)s, %(nya)s, 4, 2, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, game_number, home_team_id, "
            "away_team_id, home_score, away_score, game_type) VALUES "
            "('DH1', 2020, '2020-04-08', 1, %(atl)s, %(nya)s, 6, 5, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) "
            "VALUES ('G1', 'regular'), ('DH1', 'regular'), ('DH2', 'regular')"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, bat_home_id, resp_pit_id, resp_pit_start_fl, "
            "bat_event_fl, event_cd, event_outs_ct, _season) VALUES "
            # G1: ATL starter startp1 faces one batter (so `starters`
            # resolves), then reliever relp1 faces 2 (1 K, 1 out).
            "('G1', '0', 'startp1', 'T', 'T', '2', '1', '2020'), "
            "('G1', '0', 'relp1', 'F', 'T', '3', '1', '2020'), "  # K
            "('G1', '0', 'relp1', 'F', 'T', '2', '1', '2020'), "  # generic out
            # DH1: same starter/reliever split; relp1 faces 1 (BB).
            "('DH1', '0', 'startp1', 'T', 'T', '2', '1', '2020'), "
            "('DH1', '0', 'relp1', 'F', 'T', '14', '0', '2020'), "  # BB
            # DH2: same split; relp1's own line here is unused in assertions.
            "('DH2', '0', 'startp1', 'T', 'T', '2', '1', '2020'), "
            "('DH2', '0', 'relp1', 'F', 'T', '2', '1', '2020')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = bullpen.compute(db_conn)
    db_conn.commit()

    assert updated == 3
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT f.home_bullpen_fip, f.home_bullpen_k_pct, f.home_bullpen_bb_pct "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "WHERE g.retro_game_id = 'DH2'"
        )
        fip, k_pct, bb_pct = cur.fetchone()

    assert abs(fip - Decimal("4.60")) < Decimal("0.01")
    assert abs(k_pct - Decimal("1") / Decimal("3")) < Decimal("0.0001")
    assert abs(bb_pct - Decimal("1") / Decimal("3")) < Decimal("0.0001")

    _reset(db_conn)


def test_compute_orders_quality_window_by_coalesced_game_number_when_number_is_null(db_conn):
    # Issue #28: confirmed against real production `mlb` data that
    # Retrosheet's raw `number` field is genuinely empty for 10,020 games
    # (all 1901-1909), which conform.py turns into a NULL core.game.
    # game_number. `game_number NULLS LAST` sorts a NULL-game_number row
    # *after* any row with a real number -- wrong whenever the NULL game
    # is actually the earlier of a doubleheader pair. Same shape as
    # test_compute_orders_quality_window_by_game_number_not_insertion_order
    # above but for the NULL-number case specifically (natural insertion
    # order alone doesn't trigger this bug -- `NULLS LAST` does, regardless
    # of game_id order).
    #   G1 (2020-04-01): ATL reliever relp1 faces 2 batters (1 K, 1 out).
    #   DH1 (game_number=NULL): ATL reliever relp1 faces 1 batter (1 BB).
    #   DH2 (game_number=2): ATL reliever relp1 faces 1 batter (1 out).
    # Correctly ordered (COALESCE(game_number, 0) puts DH1 first), entering
    # DH2 pools G1 + DH1 relief: k_sum=1, bb_sum=1, bf_sum=3, hr_sum=0,
    # outs_sum=2 -- same expected values as the insertion-order regression
    # test above.
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, game_number, home_team_id, "
            "away_team_id, home_score, away_score, game_type) VALUES "
            "('G1', 2020, '2020-04-01', 1, %(atl)s, %(nya)s, 5, 3, 'regular')",
            {"atl": atl, "nya": nya},
        )
        # DH1's game_number is NULL -- the malformed-source-data case.
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, game_number, home_team_id, "
            "away_team_id, home_score, away_score, game_type) VALUES "
            "('DH1', 2020, '2020-04-08', NULL, %(atl)s, %(nya)s, 6, 5, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, game_number, home_team_id, "
            "away_team_id, home_score, away_score, game_type) VALUES "
            "('DH2', 2020, '2020-04-08', 2, %(atl)s, %(nya)s, 4, 2, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) "
            "VALUES ('G1', 'regular'), ('DH1', 'regular'), ('DH2', 'regular')"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, bat_home_id, resp_pit_id, resp_pit_start_fl, "
            "bat_event_fl, event_cd, event_outs_ct, _season) VALUES "
            "('G1', '0', 'startp1', 'T', 'T', '2', '1', '2020'), "
            "('G1', '0', 'relp1', 'F', 'T', '3', '1', '2020'), "  # K
            "('G1', '0', 'relp1', 'F', 'T', '2', '1', '2020'), "  # generic out
            "('DH1', '0', 'startp1', 'T', 'T', '2', '1', '2020'), "
            "('DH1', '0', 'relp1', 'F', 'T', '14', '0', '2020'), "  # BB
            "('DH2', '0', 'startp1', 'T', 'T', '2', '1', '2020'), "
            "('DH2', '0', 'relp1', 'F', 'T', '2', '1', '2020')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = bullpen.compute(db_conn)
    db_conn.commit()

    assert updated == 3
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT f.home_bullpen_fip, f.home_bullpen_k_pct, f.home_bullpen_bb_pct "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "WHERE g.retro_game_id = 'DH2'"
        )
        fip, k_pct, bb_pct = cur.fetchone()

    assert abs(fip - Decimal("4.60")) < Decimal("0.01")
    assert abs(k_pct - Decimal("1") / Decimal("3")) < Decimal("0.0001")
    assert abs(bb_pct - Decimal("1") / Decimal("3")) < Decimal("0.0001")

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

    _reset(db_conn)


def test_compute_returns_zero_without_retrosheet_gameinfo_table(db_conn):
    # Issue #9 item 2: compute()'s own SQL joins raw.retrosheet_gameinfo
    # too, but only retrosheet_event was gated -- see
    # test_model_offense.py's identical regression for the full explanation
    # (retrosheet_event/retrosheet_gameinfo are landed by two different
    # connectors).
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_event ("
            "game_id text, bat_home_id text, resp_pit_id text, "
            "resp_pit_start_fl text, bat_event_fl text, event_cd text, "
            "event_outs_ct text, _season text)"
        )
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gameinfo")
    db_conn.commit()

    assert bullpen.compute(db_conn) == 0

    _reset(db_conn)


def test_compute_live_rolling_fip_and_rates_match_hand_calculation(db_conn):
    # ADR-051: raw.mlb_playbyplay equivalent of the retrosheet-sourced test
    # above, same fixture shape re-dated into 2026. G1 (2026-04-01,
    # game_pk=900001): ATL (home, top half) starter startp1 faces 2 BF
    # (1 K, 1 field_out); ATL reliever relp1 then faces 3 BF (1 BB, 1 HR,
    # 1 field_out -- 1 out total, 0 K). NYA (away, bottom half) starter
    # startp2 pitches the whole game alone -- no NYA reliever appears.
    #
    # G2 (2026-04-03, 2 days later -- inside the 3-day fatigue window):
    # both teams use only their starters again.
    #
    # Entering G2, ATL's rolling bullpen line is exactly relp1's G1 line:
    #   BF=3, K=0, BB=1, HR=1, outs=1
    #   k_pct = 0, bb_pct = 1/3 = 0.33333
    #   fip = (13*1 + 3*1 - 2*0) / (1/3) + 3.10 = 48 + 3.10 = 51.1
    #   fatigue (trailing 3 days before 2026-04-03): G1 (04-01) qualifies -> 1
    # NYA never used a reliever -- quality NULL, fatigue a real 0 (the
    # team_game backbone this shares with compute()'s own _BUILD_SQL).
    _reset(db_conn)
    _ensure_playbyplay_table(db_conn)
    teams = _seed_teams_2026(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, game_pk, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('MLB900001', '900001', 2026, '2026-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('MLB900002', '900002', 2026, '2026-04-03', %(atl)s, %(nya)s, 2, 1, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.mlb_playbyplay "
            "(game_pk, at_bat_index, inning, half_inning, pitcher_id, event_type, outs, _season) "
            "VALUES "
            "('900001', '0', '1', 'top', '5001', 'strikeout', '1', '2026'), "
            "('900001', '1', '1', 'top', '5001', 'field_out', '2', '2026'), "
            "('900001', '2', '1', 'top', '5099', 'walk', '2', '2026'), "
            "('900001', '3', '1', 'top', '5099', 'home_run', '2', '2026'), "
            "('900001', '4', '1', 'top', '5099', 'field_out', '3', '2026'), "
            "('900001', '5', '1', 'bottom', '5002', 'field_out', '1', '2026'), "
            "('900002', '0', '1', 'top', '5001', 'field_out', '1', '2026'), "
            "('900002', '1', '1', 'bottom', '5002', 'field_out', '1', '2026')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = bullpen.compute_live(db_conn)
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

    g1 = rows["MLB900001"]
    assert g1 == (None, None, None, None, None, None, None, None)

    g2 = rows["MLB900002"]
    assert g2[0] == Decimal("51.1")
    assert g2[1] == Decimal("0")
    assert abs(g2[2] - Decimal("1") / Decimal("3")) < Decimal("0.0001")
    assert g2[3] == Decimal("1")
    assert g2[4] is None
    assert g2[5] is None
    assert g2[6] is None
    assert g2[7] == Decimal("0")

    _reset(db_conn)


def test_compute_live_returns_zero_without_playbyplay_table(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_playbyplay")
    db_conn.commit()

    assert bullpen.compute_live(db_conn) == 0


def test_compute_live_does_not_overwrite_retrosheet_derived_values(db_conn):
    # compute_live() must only fill the NULL gap compute() leaves -- a game
    # already resolved via raw.retrosheet_event must never be touched by
    # the playbyplay path, even if a raw.mlb_playbyplay row happens to
    # exist for it too (same discipline as starter.py's own analogous test).
    _reset(db_conn)
    _ensure_playbyplay_table(db_conn)
    _ensure_retrosheet_tables(db_conn)
    teams = _seed_teams_2026(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, game_pk, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', '900001', 2020, '2020-04-01', %(atl)s, %(nya)s, 5, 3, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute("INSERT INTO raw.retrosheet_gameinfo (gid, gametype) VALUES ('G1', 'regular')")
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, bat_home_id, resp_pit_id, resp_pit_start_fl, "
            "bat_event_fl, event_cd, event_outs_ct, _season) VALUES "
            "('G1', '0', 'startp1', 'T', 'T', '2', '1', '2020')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    bullpen.compute(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_bullpen_fip FROM gold.game_feature f "
            "JOIN core.game g ON g.id = f.game_id WHERE g.retro_game_id = 'G1'"
        )
        before = cur.fetchone()

    bullpen.compute_live(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_bullpen_fip FROM gold.game_feature f "
            "JOIN core.game g ON g.id = f.game_id WHERE g.retro_game_id = 'G1'"
        )
        after = cur.fetchone()

    assert before == after

    _reset(db_conn)


def test_compute_upcoming_rolls_up_team_history_with_zero_leakage(db_conn):
    # ADR-051: unlike starter.py's compute_probable(), no raw.mlb_probable
    # dependency at all -- bullpen quality/fatigue is team-level, resolved
    # straight from gold.game_feature's own home_team_id/away_team_id
    # (already set by features.py for every upcoming row). Same fixture
    # shape as compute_live's test above: G1 (2026-04-01, completed, in
    # core.game) gives ATL a real relief line; the upcoming game
    # (2026-04-03, raw.mlb_schedule status='Scheduled', not yet in
    # core.game at all) should resolve the exact same rolling values.
    _reset(db_conn)
    _ensure_playbyplay_table(db_conn)
    _ensure_mlb_schedule_table(db_conn)
    teams = _seed_teams_2026(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, game_pk, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('MLB900001', '900001', 2026, '2026-04-01', %(atl)s, %(nya)s, 5, 3, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.mlb_playbyplay "
            "(game_pk, at_bat_index, inning, half_inning, pitcher_id, event_type, outs, _season) "
            "VALUES "
            "('900001', '0', '1', 'top', '5001', 'strikeout', '1', '2026'), "
            "('900001', '1', '1', 'top', '5001', 'field_out', '2', '2026'), "
            "('900001', '2', '1', 'top', '5099', 'walk', '2', '2026'), "
            "('900001', '3', '1', 'top', '5099', 'home_run', '2', '2026'), "
            "('900001', '4', '1', 'top', '5099', 'field_out', '3', '2026'), "
            "('900001', '5', '1', 'bottom', '5002', 'field_out', '1', '2026')"
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, _season, game_date, game_type, status, home_id, away_id) VALUES "
            "('900002', '2026', '2026-04-03', 'R', 'Scheduled', '144', '147')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = bullpen.compute_upcoming(db_conn)
    db_conn.commit()

    assert updated == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_bullpen_fip, home_bullpen_k_pct, home_bullpen_bb_pct, "
            "home_bullpen_fatigue, away_bullpen_fip, away_bullpen_k_pct, "
            "away_bullpen_bb_pct, away_bullpen_fatigue "
            "FROM gold.game_feature WHERE mlb_game_pk = '900002'"
        )
        row = cur.fetchone()

    assert row[0] == Decimal("51.1")
    assert row[1] == Decimal("0")
    assert abs(row[2] - Decimal("1") / Decimal("3")) < Decimal("0.0001")
    assert row[3] == Decimal("1")
    # NYA never used a reliever in any qualifying prior game -- unlike
    # compute_live/compute()'s team_game backbone, compute_upcoming() has
    # no backbone (see its own docstring), so a team with zero qualifying
    # relief appearances resolves fatigue NULL here, not a real 0.
    assert row[4] is None
    assert row[5] is None
    assert row[6] is None
    assert row[7] is None

    _reset(db_conn)


def test_compute_upcoming_only_uses_history_strictly_before_target_game_date(db_conn):
    _reset(db_conn)
    _ensure_playbyplay_table(db_conn)
    _ensure_mlb_schedule_table(db_conn)
    teams = _seed_teams_2026(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, game_pk, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('MLB900001', '900001', 2026, '2026-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('MLB900003', '900003', 2026, '2026-04-20', %(atl)s, %(nya)s, 2, 1, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.mlb_playbyplay "
            "(game_pk, at_bat_index, inning, half_inning, pitcher_id, event_type, outs, _season) "
            "VALUES "
            # Prior (before the target's 2026-04-15 date): ATL relief
            # BF=2 (1 BB, 1 field_out), outs=1.
            "('900001', '0', '1', 'top', '5001', 'field_out', '1', '2026'), "
            "('900001', '1', '1', 'top', '5099', 'walk', '1', '2026'), "
            "('900001', '2', '1', 'top', '5099', 'field_out', '2', '2026'), "
            "('900001', '3', '1', 'bottom', '5002', 'field_out', '1', '2026'), "
            # After the target's date -- must NOT count toward it. If it
            # did, the reliever's HR here would shift fip from 12.1 up to
            # (13*1 + 3*1 - 2*0)/(2/3) + 3.10 = 27 + 3.10 = 30.1.
            "('900003', '0', '1', 'top', '5001', 'field_out', '1', '2026'), "
            "('900003', '1', '1', 'top', '5099', 'home_run', '1', '2026'), "
            "('900003', '2', '1', 'bottom', '5002', 'field_out', '1', '2026')"
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, _season, game_date, game_type, status, home_id, away_id) VALUES "
            "('900002', '2026', '2026-04-15', 'R', 'Scheduled', '144', '147')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    bullpen.compute_upcoming(db_conn)
    db_conn.commit()

    # ATL relief prior-only: BF=2, K=0, BB=1, HR=0, outs=1.
    # fip = (13*0 + 3*1 - 2*0)/(1/3) + 3.10 = 9 + 3.10 = 12.1 -- if the
    # later game's HR leaked in, this would be 30.1 instead (see above).
    with db_conn.cursor() as cur:
        cur.execute("SELECT home_bullpen_fip FROM gold.game_feature WHERE mlb_game_pk = '900002'")
        (fip,) = cur.fetchone()
    assert fip == Decimal("12.1")

    _reset(db_conn)


def test_compute_upcoming_returns_zero_without_playbyplay_table(db_conn):
    _reset(db_conn)
    _ensure_mlb_schedule_table(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_playbyplay")
    db_conn.commit()

    assert bullpen.compute_upcoming(db_conn) == 0


def test_health_check_flags_missing_upcoming_coverage(db_conn):
    # A team has real, qualifying prior 2026 relief history, but
    # home_bullpen_fip never got filled in for an upcoming game against
    # them -- exactly what a broken compute_upcoming() run would look
    # like. Six upcoming games, not one: check_join_coverage's tolerance
    # (5) absorbs a handful of mismatches as a known, accepted edge case,
    # a single missed row must not trip a doctor alert on that basis
    # alone, but six genuinely should.
    _reset(db_conn)
    _ensure_playbyplay_table(db_conn)
    _ensure_mlb_schedule_table(db_conn)
    teams = _seed_teams_2026(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, game_pk, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('MLB900001', '900001', 2026, '2026-04-01', %(atl)s, %(nya)s, 5, 3, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.mlb_playbyplay "
            "(game_pk, at_bat_index, inning, half_inning, pitcher_id, event_type, outs, _season) "
            "VALUES "
            "('900001', '0', '1', 'top', '5001', 'field_out', '1', '2026'), "
            "('900001', '1', '1', 'top', '5099', 'walk', '1', '2026'), "
            "('900001', '2', '1', 'bottom', '5002', 'field_out', '1', '2026')"
        )
        for i in range(6):
            cur.execute(
                "INSERT INTO raw.mlb_schedule "
                "(game_id, _season, game_date, game_type, status, home_id, away_id) "
                "VALUES (%s, '2026', '2026-04-15', 'R', 'Scheduled', '144', '147')",
                (f"90006{i}",),
            )
    db_conn.commit()
    features.build(db_conn)
    db_conn.commit()
    # Deliberately NOT calling bullpen.compute_upcoming() -- home_bullpen_fip
    # stays NULL for all six despite a real, resolvable history existing.

    checks = bullpen.health_check()
    check = next(c for c in checks if c.name == "upcoming games get a resolved bullpen feature")
    assert not check.ok

    _reset(db_conn)


def test_health_check_runs_cleanly_against_an_empty_database():
    checks = bullpen.health_check()
    assert len(checks) == 2
    assert all(c.name for c in checks)
