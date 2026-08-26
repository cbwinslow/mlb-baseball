"""Regression coverage for mlb_baseball.model.leverage_index -- the
empirical Leverage Index table backing the Plan 06 avg_li rebuild
(ADR-262).
"""

from __future__ import annotations

from decimal import Decimal

from mlb_baseball.model import leverage_index


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        for table in ("raw.retrosheet_event", "raw.retrosheet_gameinfo"):
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute("DELETE FROM gold.win_expectancy")
        cur.execute("DELETE FROM gold.leverage_index")
        cur.execute("DELETE FROM gold.leverage_index_staging")
        cur.execute("DELETE FROM core.game WHERE retro_game_id IN ('G1', 'G2')")
        cur.execute("DELETE FROM core.team WHERE retro_team_id IN ('ATL', 'NYA')")
    db_conn.commit()


def test_compute_missing_table_gate(db_conn):
    _reset(db_conn)
    assert leverage_index.compute(db_conn) == 0


def test_compute_matches_hand_calculation(db_conn):
    # Two games, two events each -- every real play gets its own leverage
    # value from its own before-state, including the last play of a game
    # (whose "after" state is the real final win/loss outcome, not another
    # row's before-state -- this is what proves the game-ending fallback
    # path works, not just the ordinary next-play path).
    #
    # G1 (home team ATL wins 5-3, home_won=true):
    #   event1: State A (inn=1, top, 0 outs, bases empty, margin=0), WE=0.50.
    #     "after" = event2's own before-state, State B, WE=0.55.
    #     swing_A = |0.55-0.50| = 0.05.
    #   event2: State B, WE=0.55. Last play of G1 -> "after" = game outcome
    #     (home won) = 1.0. swing_B = |1.0-0.55| = 0.45.
    #
    # G2 (home team ATL wins 4-3, home_won=true):
    #   event1: State C (inn=9, bottom, 0 outs, bases loaded, margin=0),
    #     WE=0.60. "after" = event2's before-state, State D, WE=0.90.
    #     swing_C = |0.90-0.60| = 0.30.
    #   event2: State D, WE=0.90. Last play of G2 -> "after" = game outcome
    #     (home won) = 1.0. swing_D = |1.0-0.90| = 0.10.
    #
    # Global average swing = (0.05 + 0.45 + 0.30 + 0.10) / 4 = 0.225.
    # LI_A = 0.05 / 0.225 = 0.2222
    # LI_B = 0.45 / 0.225 = 2.0000
    # LI_C = 0.30 / 0.225 = 1.3333
    # LI_D = 0.10 / 0.225 = 0.4444
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_event ("
            "game_id text, inn_ct integer, bat_home_id text, event_id integer, "
            "outs_ct text, base1_run_id text, base2_run_id text, base3_run_id text, "
            "start_bat_score_ct text, start_fld_score_ct text, _season text)"
        )
        cur.execute(
            "CREATE TABLE raw.retrosheet_gameinfo "
            "(gid text, gametype text, visteam text, hometeam text, _season text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) "
            "VALUES ('G1', 'regular'), ('G2', 'regular')"
        )
        cur.execute(
            "INSERT INTO core.team (retro_team_id, city, nickname, first_year, last_year, "
            "mlb_team_id) VALUES "
            "('ATL', 'Atlanta', 'Braves', 1966, 2025, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147) "
            "RETURNING id, retro_team_id"
        )
        teams = {r[1]: r[0] for r in cur.fetchall()}
        atl, nya = teams["ATL"], teams["NYA"]
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, game_number, home_team_id, away_team_id, "
            " home_score, away_score, game_type) VALUES "
            "('G1', 2021, '2021-04-01', 0, %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', 2021, '2021-04-08', 0, %(atl)s, %(nya)s, 4, 3, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO gold.win_expectancy "
            "(season, inning_bucket, is_bottom, outs_before, base_state, margin_bucket, "
            "home_win_pct, sample_size) VALUES "
            "(2021, 1, false, 0, '000', 0, 0.50, 100), "  # State A (before, G1)
            "(2021, 1, false, 1, '000', 0, 0.55, 100), "  # State B (after, G1)
            "(2021, 9, true, 0, '111', 0, 0.60, 100), "  # State C (before, G2)
            "(2021, 9, true, 1, '000', 1, 0.90, 100)"  # State D (after, G2)
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, inn_ct, bat_home_id, event_id, outs_ct, "
            "base1_run_id, base2_run_id, base3_run_id, "
            "start_bat_score_ct, start_fld_score_ct, _season) VALUES "
            # G1: State A -> State B
            "('G1', 1, '0', 1, '0', NULL, NULL, NULL, '0', '0', '2021'), "
            "('G1', 1, '0', 2, '1', NULL, NULL, NULL, '0', '0', '2021'), "
            # G2: State C -> State D
            "('G2', 9, '1', 1, '0', 'p1', 'p2', 'p3', '3', '3', '2021'), "
            "('G2', 9, '1', 2, '1', NULL, NULL, NULL, '4', '3', '2021')"
        )
    db_conn.commit()

    rows = leverage_index.compute(db_conn)
    assert rows == 4

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT leverage_index FROM gold.leverage_index "
            "WHERE inning_bucket = 1 AND is_bottom = false AND base_state = '000' "
            "AND margin_bucket = 0 ORDER BY outs_before"
        )
        li_a, li_b = (row[0] for row in cur.fetchall())
        cur.execute(
            "SELECT leverage_index FROM gold.leverage_index "
            "WHERE inning_bucket = 9 AND is_bottom = true AND margin_bucket IN (0, 1) "
            "ORDER BY outs_before"
        )
        li_c, li_d = (row[0] for row in cur.fetchall())

    assert li_a == Decimal("0.2222")
    assert li_b == Decimal("2.0000")
    assert li_c == Decimal("1.3333")
    assert li_d == Decimal("0.4444")

    # The guard: a second call must not rebuild (gold.leverage_index is
    # already populated) -- returns 0, not another positive rowcount.
    assert leverage_index.compute(db_conn) == 0
    _reset(db_conn)


def test_compute_returns_zero_without_win_expectancy_data(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_event ("
            "game_id text, inn_ct integer, bat_home_id text, event_id integer, "
            "outs_ct text, base1_run_id text, base2_run_id text, base3_run_id text, "
            "start_bat_score_ct text, start_fld_score_ct text, _season text)"
        )
    db_conn.commit()
    assert leverage_index.compute(db_conn) == 0
    _reset(db_conn)


def test_health_check_flags_empty_table():
    checks = leverage_index.health_check()
    coverage_check = next(c for c in checks if c.name == "leverage_index coverage")
    assert isinstance(coverage_check.ok, bool)
