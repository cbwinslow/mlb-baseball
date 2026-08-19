"""Regression coverage for mlb_baseball.model.markov -- base/out transition
matrix estimation from raw.retrosheet_event (Plan 04D).
"""

import pytest

from mlb_baseball.model import markov


def _ensure_retrosheet_tables(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.retrosheet_event ("
                "game_id text, outs_ct text, event_outs_ct text, event_cd text, "
                "base1_run_id text, base2_run_id text, base3_run_id text, "
                "bat_dest_id text, run1_dest_id text, run2_dest_id text, run3_dest_id text)"
            )
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.retrosheet_gameinfo (gid text, gametype text, _season text)"
            )
    db_conn.commit()


def _reset(db_conn):
    # DROPs, not DELETEs, matching every other test_model_*.py file's own
    # raw.retrosheet_event/retrosheet_gameinfo stub-table convention
    # (issue #7) -- a stub left behind with a different column set by
    # whichever file's tests happen to run first in a full-suite session
    # would otherwise break this file's own schema expectations.
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gameinfo")
    db_conn.commit()


def _insert_event(
    cur,
    game_id,
    outs_ct,
    event_outs_ct,
    event_cd,
    *,
    b1=None,
    b2=None,
    b3=None,
    bat_dest="0",
    r1_dest="0",
    r2_dest="0",
    r3_dest="0",
):
    cur.execute(
        "INSERT INTO raw.retrosheet_event "
        "(game_id, outs_ct, event_outs_ct, event_cd, base1_run_id, base2_run_id, "
        "base3_run_id, bat_dest_id, run1_dest_id, run2_dest_id, run3_dest_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            game_id,
            outs_ct,
            event_outs_ct,
            event_cd,
            b1,
            b2,
            b3,
            bat_dest,
            r1_dest,
            r2_dest,
            r3_dest,
        ),
    )


def test_estimate_transition_matrix_matches_hand_built_half_inning(db_conn):
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype, _season) "
            "VALUES ('G1', 'regular', '2021'), ('G2', 'regular', '2021'), "
            "('G3', 'playoff', '2021'), ('G4', 'regular', '2019')"
        )
        # G1: leadoff single (empty/0 -> 1st/0), then a strikeout with the
        # runner held at first (1st/0 -> 1st/1), then a double play ending
        # the inning with no runs (1st/1 -> TERMINAL).
        _insert_event(cur, "G1", "0", "0", "20", bat_dest="1")
        _insert_event(cur, "G1", "0", "1", "3", b1="r1", bat_dest="0", r1_dest="1")
        _insert_event(cur, "G1", "1", "2", "2", b1="r1", bat_dest="0", r1_dest="0")
        # G2: same regular-season year, a second leadoff single (empty/0 ->
        # 1st/0) so the aggregated count across games is exercised, plus a
        # bases-loaded double scoring 2 and leaving runners on 2nd/3rd
        # (loaded/1 -> 2nd+3rd/1, 2 runs) to exercise runs_scored > 0.
        _insert_event(cur, "G2", "0", "0", "20", bat_dest="1")
        _insert_event(
            cur,
            "G2",
            "1",
            "0",
            "21",
            b1="r1",
            b2="r2",
            b3="r3",
            bat_dest="2",
            r1_dest="4",
            r2_dest="4",
            r3_dest="3",
        )
        # G3: playoff game, same shape as G1's first play -- must be
        # excluded entirely by the regular-season filter.
        _insert_event(cur, "G3", "0", "0", "20", bat_dest="1")
        # G4: regular season but a different year (2019) -- must be
        # excluded when querying only season 2021.
        _insert_event(cur, "G4", "0", "0", "20", bat_dest="1")
    db_conn.commit()

    matrix = markov.estimate_transition_matrix(db_conn, seasons=[2021])

    empty_zero = markov.BaseOutState(0, False, False, False)
    first_zero = markov.BaseOutState(0, True, False, False)
    first_one = markov.BaseOutState(1, True, False, False)
    loaded_one = markov.BaseOutState(1, True, True, True)
    second_third_one = markov.BaseOutState(1, False, True, True)

    # Both G1 and G2's leadoff singles land in the same (empty/0 -> 1st/0)
    # bucket -- must aggregate to a count of 2, i.e. probability 1.0 since
    # it is that pre-state's only observed outcome in this fixture.
    assert matrix[empty_zero][first_zero] == 1.0
    assert matrix[first_one][markov.TERMINAL] == 1.0
    # The runner held at first: 1st/0 -> 1st/1, this fixture's only
    # observed transition from that pre-state.
    assert matrix[first_zero][first_one] == 1.0
    assert matrix[loaded_one][second_third_one] == 1.0
    # Playoff (G3) and off-season-year (G4) rows must not leak into the
    # season-2021-regular-only estimate: if they had, empty_zero's total
    # observed count would be 4, not 2, and this leadoff-single transition
    # would still show 1.0 either way -- the real proof is a snapshot
    # excluding 2019/playoff below.
    assert set(matrix[empty_zero]) == {first_zero}


def test_estimate_transition_matrix_excludes_other_seasons_and_gametypes(db_conn):
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype, _season) "
            "VALUES ('G1', 'regular', '2021'), ('G2', 'playoff', '2021'), "
            "('G3', 'regular', '2019')"
        )
        # G1 (regular, 2021): single then a strikeout ending the inning.
        _insert_event(cur, "G1", "0", "0", "20", bat_dest="1")
        _insert_event(cur, "G1", "0", "1", "3", b1="r1", bat_dest="0", r1_dest="1")
        # G2 (playoff, 2021): a home run that would score a run if counted.
        _insert_event(cur, "G2", "0", "0", "23", bat_dest="4")
        # G3 (regular, 2019): a home run that would score a run if counted.
        _insert_event(cur, "G3", "0", "0", "23", bat_dest="4")
    db_conn.commit()

    matrix = markov.estimate_transition_matrix(db_conn, seasons=[2021])

    empty_zero = markov.BaseOutState(0, False, False, False)
    # If G2's playoff HR or G3's 2019 HR had leaked in, empty_zero would
    # also transition to TERMINAL-via-scoring or show a second outcome --
    # only G1's single-then-K sequence should be present.
    assert set(matrix[empty_zero]) == {markov.BaseOutState(0, True, False, False)}


def test_estimate_run_expectancy_matches_hand_calculation(db_conn):
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype, _season) "
            "VALUES ('G1', 'regular', '2021'), ('G2', 'regular', '2021')"
        )
        # G1: single (empty/0 -> 1st/0), K holding the runner (1st/0 ->
        # 1st/1), double play ending the inning (1st/1 -> TERMINAL, 0 runs)
        # -- a deterministic chain with 0 runs scored anywhere in it, so
        # every state in it hand-computes to RE=0.
        _insert_event(cur, "G1", "0", "0", "20", bat_dest="1")
        _insert_event(cur, "G1", "0", "1", "3", b1="r1", bat_dest="0", r1_dest="1")
        _insert_event(cur, "G1", "1", "2", "2", b1="r1", bat_dest="0", r1_dest="0")
        # G2: a bases-loaded double scoring 2, leaving runners on 2nd/3rd
        # (loaded/1 -> 2nd+3rd/1, runs=2). 2nd+3rd/1 out never appears as
        # its own pre-state anywhere in this small fixture, so its RE
        # defaults to 0 (run_expectancy's documented fallback for a state
        # with no observed outgoing transitions) -- hand-computed:
        # RE(loaded/1) = 1.0 * (2 + RE(2nd+3rd/1)) = 1.0 * (2 + 0) = 2.0.
        _insert_event(
            cur,
            "G2",
            "1",
            "0",
            "21",
            b1="r1",
            b2="r2",
            b3="r3",
            bat_dest="2",
            r1_dest="4",
            r2_dest="4",
            r3_dest="3",
        )
    db_conn.commit()

    re = markov.estimate_run_expectancy(db_conn, seasons=[2021])

    empty_zero = markov.BaseOutState(0, False, False, False)
    first_zero = markov.BaseOutState(0, True, False, False)
    first_one = markov.BaseOutState(1, True, False, False)
    loaded_one = markov.BaseOutState(1, True, True, True)

    assert re[first_one] == pytest.approx(0.0)
    assert re[first_zero] == pytest.approx(0.0)
    assert re[empty_zero] == pytest.approx(0.0)
    assert re[loaded_one] == pytest.approx(2.0)
