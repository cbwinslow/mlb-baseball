"""Integration tests for high-throughput vectorized Monte Carlo Markov game simulation (ADR-105)."""

# ruff: noqa: E501

import pytest

from mlb_baseball.model import markov
from mlb_baseball.model.simulate import (
    DenseOutcomeTable,
    simulate_games_fast,
    simulate_live_game_fast,
)


def _ensure_retrosheet_tables(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.retrosheet_event ("
                "game_id text, inn_ct text, bat_home_id text, "
                "outs_ct text, event_outs_ct text, event_cd text, "
                "base1_run_id text, base2_run_id text, base3_run_id text, "
                "bat_dest_id text, run1_dest_id text, run2_dest_id text, run3_dest_id text)"
            )
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.retrosheet_gameinfo "
                "(gid text, gametype text, _season text, vruns text, hruns text)"
            )
    db_conn.commit()


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gameinfo")
    db_conn.commit()


def _seed_sample_game(db_conn, season=2019):
    _ensure_retrosheet_tables(db_conn)
    gid = f"BOS{season}04010"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype, _season, vruns, hruns) "
            "VALUES (%s, 'regular', %s, '3', '4')",
            (gid, str(season)),
        )
        # 1. 0 out empty -> single (0 out on 1st)
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, inn_ct, bat_home_id, outs_ct, event_outs_ct, event_cd, "
            "base1_run_id, base2_run_id, base3_run_id, bat_dest_id, run1_dest_id, run2_dest_id, run3_dest_id) "
            "VALUES (%s, '1', '0', '0', '0', '20', NULL, NULL, NULL, '1', '0', '0', '0')",
            (gid,),
        )
        # 2. 0 out on 1st -> HR (0 out empty, 2 runs)
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, inn_ct, bat_home_id, outs_ct, event_outs_ct, event_cd, "
            "base1_run_id, base2_run_id, base3_run_id, bat_dest_id, run1_dest_id, run2_dest_id, run3_dest_id) "
            "VALUES (%s, '1', '0', '0', '0', '23', 'r1', NULL, NULL, '4', '4', '0', '0')",
            (gid,),
        )
        # 3. 0 out empty -> strikeout (1 out empty)
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, inn_ct, bat_home_id, outs_ct, event_outs_ct, event_cd, "
            "base1_run_id, base2_run_id, base3_run_id, bat_dest_id, run1_dest_id, run2_dest_id, run3_dest_id) "
            "VALUES (%s, '1', '0', '0', '1', '3', NULL, NULL, NULL, '0', '0', '0', '0')",
            (gid,),
        )
        # 4. 1 out empty -> strikeout (2 out empty)
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, inn_ct, bat_home_id, outs_ct, event_outs_ct, event_cd, "
            "base1_run_id, base2_run_id, base3_run_id, bat_dest_id, run1_dest_id, run2_dest_id, run3_dest_id) "
            "VALUES (%s, '1', '0', '1', '1', '3', NULL, NULL, NULL, '0', '0', '0', '0')",
            (gid,),
        )
        # 5. 2 out empty -> groundout (3 out / TERMINAL)
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, inn_ct, bat_home_id, outs_ct, event_outs_ct, event_cd, "
            "base1_run_id, base2_run_id, base3_run_id, bat_dest_id, run1_dest_id, run2_dest_id, run3_dest_id) "
            "VALUES (%s, '1', '0', '2', '1', '2', NULL, NULL, NULL, '0', '0', '0', '0')",
            (gid,),
        )
    db_conn.commit()


def test_simulate_games_end_to_end_from_postgres(db_conn):
    """Verify DenseOutcomeTable construction from real PostgreSQL event records and simulation."""
    _reset(db_conn)
    _seed_sample_game(db_conn, season=2019)

    dist = markov.estimate_outcome_distribution(db_conn, seasons=[2019])
    assert len(dist) > 0

    table = DenseOutcomeTable.from_distribution(dist)
    summary = simulate_games_fast(
        home_table=table,
        away_table=table,
        n_simulations=1000,
        seed=42,
    )

    assert summary.simulations_run == 1000
    assert summary.home_win_prob + summary.away_win_prob == pytest.approx(1.0, abs=1e-4)
    assert summary.expected_total_runs > 0
    assert summary.duration_ms > 0
    assert summary.simulations_per_sec > 0
    _reset(db_conn)


def test_simulate_live_game_end_to_end_from_postgres(db_conn):
    """Verify live in-game simulation from PostgreSQL event matrix."""
    _reset(db_conn)
    _seed_sample_game(db_conn, season=2019)

    dist = markov.estimate_outcome_distribution(db_conn, seasons=[2019])
    table = DenseOutcomeTable.from_distribution(dist)

    start_state = markov.BaseOutState(outs=1, on1=True, on2=False, on3=False)
    live_summary = simulate_live_game_fast(
        home_table=table,
        away_table=table,
        current_inning=7,
        is_bottom_half=False,
        current_state=start_state,
        home_score=3,
        away_score=2,
        n_simulations=1000,
        seed=100,
    )

    assert live_summary.simulations_run == 1000
    assert live_summary.home_win_prob + live_summary.away_win_prob == pytest.approx(1.0, abs=1e-4)
    assert live_summary.expected_final_home_runs >= 3.0
    assert live_summary.expected_final_away_runs >= 2.0
    _reset(db_conn)
