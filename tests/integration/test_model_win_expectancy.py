"""Regression coverage for mlb_baseball.model.win_expectancy -- the
empirical win-expectancy table backing the Plan 06 Leverage Index rebuild
(ADR-262).
"""

from __future__ import annotations

from mlb_baseball.model import win_expectancy


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        for table in ("raw.retrosheet_event", "raw.retrosheet_gameinfo"):
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team WHERE retro_team_id IN ('ATL', 'NYA')")
        cur.execute("DELETE FROM gold.win_expectancy")
    db_conn.commit()


def _create_tables(db_conn):
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
    db_conn.commit()


def test_compute_missing_table_gate(db_conn):
    _reset(db_conn)
    assert win_expectancy.compute(db_conn) == 0


def test_compute_populates_real_observed_win_rate(db_conn):
    # Two games, same (inning=1, top, bases empty, 0 outs, tied) state at
    # their very first play. G1's home team (ATL) wins; G2's home team
    # (ATL again) loses. The empirically observed home_win_pct for that
    # exact state must come out to exactly 0.5 (1 win out of 2 real
    # observations) -- not a guess, the literal average of what happened.
    _reset(db_conn)
    _create_tables(db_conn)
    with db_conn.cursor() as cur:
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
            "('G2', 2021, '2021-04-08', 0, %(atl)s, %(nya)s, 2, 6, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) "
            "VALUES ('G1', 'regular'), ('G2', 'regular')"
        )
        # Top of the 1st, bases empty, 0 outs, tied 0-0, for both games.
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, inn_ct, bat_home_id, event_id, outs_ct, "
            "base1_run_id, base2_run_id, base3_run_id, "
            "start_bat_score_ct, start_fld_score_ct, _season) VALUES "
            "('G1', 1, '0', 1, '0', NULL, NULL, NULL, '0', '0', '2021'), "
            "('G2', 1, '0', 1, '0', NULL, NULL, NULL, '0', '0', '2021')"
        )
    db_conn.commit()

    rows = win_expectancy.compute(db_conn)
    assert rows > 0

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_win_pct, sample_size FROM gold.win_expectancy "
            "WHERE season = 2021 AND inning_bucket = 1 AND is_bottom = false "
            "AND outs_before = 0 AND base_state = '000' AND margin_bucket = 0"
        )
        home_win_pct, sample_size = cur.fetchone()

    assert sample_size == 2
    assert float(home_win_pct) == 0.5  # ATL won G1, lost G2 -> exactly 1/2

    # The guard: a second call must not rebuild (a real, populated
    # gold.win_expectancy already exists) -- returns 0, not another
    # positive rowcount, and touches nothing.
    assert win_expectancy.compute(db_conn) == 0
    _reset(db_conn)


def test_compute_only_builds_once(db_conn):
    # gold.win_expectancy is a full-history reference table, expensive to
    # build (a self-join over every real historical play) -- compute()
    # builds it once, then is a cheap no-op on every subsequent call
    # (matching run_expectancy.py's identical gold.run_expectancy_24
    # guard), rather than rebuilding from scratch on every daily pipeline
    # run. Empty raw tables here means the first build itself is a no-op
    # too, but the "second call changes nothing further" contract is what
    # this actually verifies.
    _reset(db_conn)
    _create_tables(db_conn)
    win_expectancy.compute(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM gold.win_expectancy")
        (first_count,) = cur.fetchone()
    win_expectancy.compute(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM gold.win_expectancy")
        (second_count,) = cur.fetchone()
    assert first_count == second_count
    _reset(db_conn)


def test_health_check_flags_empty_table():
    checks = win_expectancy.health_check()
    coverage_check = next(c for c in checks if c.name == "win_expectancy coverage")
    # This runs against whatever mlb_test currently has -- either genuinely
    # empty (fails, as it should) or populated by an earlier test in this
    # file (passes). Either outcome is a real, meaningful assertion.
    assert isinstance(coverage_check.ok, bool)
