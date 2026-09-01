"""Regression coverage for mlb_baseball.model.markov -- base/out transition
matrix estimation from raw.retrosheet_event (Plan 04D).
"""

import random
from datetime import date

import pytest

from mlb_baseball.model import markov


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
                "(gid text, gametype text, _season text, vruns text, hruns text, "
                "date text)"
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
    inn_ct="1",
    bat_home_id="0",
    b1=None,
    b2=None,
    b3=None,
    bat_dest="0",
    r1_dest="0",
    r2_dest="0",
    r3_dest="0",
    resp_pit_id=None,
    bat_event_fl=None,
):
    columns = (
        "game_id, inn_ct, bat_home_id, outs_ct, event_outs_ct, event_cd, "
        "base1_run_id, base2_run_id, "
        "base3_run_id, bat_dest_id, run1_dest_id, run2_dest_id, run3_dest_id"
    )
    values: list[object] = [
        game_id,
        inn_ct,
        bat_home_id,
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
    ]
    if resp_pit_id is not None:
        columns += ", resp_pit_id"
        values.append(resp_pit_id)
    if bat_event_fl is not None:
        columns += ", bat_event_fl"
        values.append(bat_event_fl)
    placeholders = ", ".join(["%s"] * len(values))
    cur.execute(
        f"INSERT INTO raw.retrosheet_event ({columns}) VALUES ({placeholders})",
        values,
    )


def _ensure_matchup_columns(db_conn):
    """Layer-2 filters need team and pitcher columns the league query does not."""
    with db_conn.cursor() as cur:
        cur.execute(
            "ALTER TABLE raw.retrosheet_gameinfo "
            "ADD COLUMN IF NOT EXISTS visteam text, "
            "ADD COLUMN IF NOT EXISTS hometeam text, "
            "ADD COLUMN IF NOT EXISTS date text"
        )
        cur.execute(
            "ALTER TABLE raw.retrosheet_event "
            "ADD COLUMN IF NOT EXISTS resp_pit_id text, "
            "ADD COLUMN IF NOT EXISTS bat_event_fl text"
        )
    db_conn.commit()


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


def test_estimate_transition_matrix_excludes_event_codes_zero_and_one(db_conn):
    # PR review finding: the SQL's `event_cd NOT IN ('0', '1')` filter was
    # only proven absent from *current* data (a GROUP BY scan), never
    # proven to actually work mechanically -- a regression that silently
    # dropped or reversed the filter would have gone uncaught. Each
    # excluded row here is wired to produce a distinct, easy-to-detect
    # outcome (scoring a run from empty bases) if it leaked in.
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype, _season) "
            "VALUES ('G1', 'regular', '2021')"
        )
        # The only row that should survive: a leadoff single.
        _insert_event(cur, "G1", "0", "0", "20", bat_dest="1")
        # event_cd='0' (unknown) -- would score a run from empty bases if
        # counted, which no real single-into-1st transition produces.
        _insert_event(cur, "G1", "0", "0", "0", bat_dest="4")
        # event_cd='1' (no play, e.g. a substitution) -- same distinct,
        # detectable outcome if it leaked in.
        _insert_event(cur, "G1", "0", "0", "1", bat_dest="4")
    db_conn.commit()

    matrix = markov.estimate_transition_matrix(db_conn, seasons=[2021])

    empty_zero = markov.BaseOutState(0, False, False, False)
    first_zero = markov.BaseOutState(0, True, False, False)
    assert set(matrix[empty_zero]) == {first_zero}
    assert matrix[empty_zero][first_zero] == 1.0


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


def test_estimate_transition_matrix_returns_empty_when_tables_missing(db_conn):
    # Two-table readiness gate (PR review finding), matching team_rate.py/
    # offense.py/starter.py's own established convention: a fresh or
    # partially bootstrapped database (either table not yet ingested) must
    # return the same "no evidence yet" empty result every sibling
    # retrosheet_event consumer gives, not raise UndefinedTable.
    _reset(db_conn)
    assert markov.estimate_transition_matrix(db_conn, seasons=[2021]) == {}
    assert markov.estimate_run_expectancy(db_conn, seasons=[2021]) == {}


def test_estimate_transition_matrix_returns_empty_when_only_one_table_exists(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("CREATE TABLE raw.retrosheet_gameinfo (gid text, gametype text, _season text)")
    db_conn.commit()
    assert markov.estimate_transition_matrix(db_conn, seasons=[2021]) == {}


def test_estimate_outcome_distribution_keeps_runs_scored_and_simulates(db_conn):
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype, _season) "
            "VALUES ('G1', 'regular', '2021')"
        )
        # A deterministic single-path half-inning, each state visited
        # exactly once (empty/0, 1st/0, 1st/1, TERMINAL -- no revisits, so
        # every pre-state has exactly one observed outcome):
        # leadoff single (empty/0 -> 1st/0, 0 runs), a strikeout holding
        # the runner (1st/0 -> 1st/1, 0 runs), then the third out on a
        # play that also scores the runner from 1st (1st/1 -> TERMINAL,
        # 1 run).
        _insert_event(cur, "G1", "0", "0", "20", bat_dest="1")
        _insert_event(cur, "G1", "0", "1", "3", b1="r1", bat_dest="0", r1_dest="1")
        _insert_event(cur, "G1", "1", "2", "2", b1="r1", bat_dest="0", r1_dest="4")
    db_conn.commit()

    distribution = markov.estimate_outcome_distribution(db_conn, seasons=[2021])

    empty_zero = markov.BaseOutState(0, False, False, False)
    first_zero = markov.BaseOutState(0, True, False, False)
    first_one = markov.BaseOutState(1, True, False, False)
    assert distribution[empty_zero][markov.Outcome(first_zero, 0)] == 1.0
    assert distribution[first_zero][markov.Outcome(first_one, 0)] == 1.0
    assert distribution[first_one][markov.Outcome(markov.TERMINAL, 1)] == 1.0

    # The whole chain is deterministic (every state has exactly one
    # observed outcome), so simulating it must always sum to the same
    # total regardless of the RNG seed: 0 (single) + 0 (K, runner held) +
    # 1 (the play ending the inning also scores the runner) = 1.
    runs = markov.simulate_half_inning(distribution, random.Random(0))
    assert runs == 1


def test_estimate_outcome_distribution_returns_empty_when_tables_missing(db_conn):
    _reset(db_conn)
    assert markov.estimate_outcome_distribution(db_conn, seasons=[2021]) == {}


def test_estimate_outcome_distribution_bat_home_filters_to_one_side(db_conn):
    # Both plays go straight from empty/0 to TERMINAL in one play (an
    # unrealistic combination of outs/scoring for a single real play, but
    # a valid, minimal fixture -- event_outs_ct=3 reaches 3 outs
    # immediately regardless of what else happens on the play). G1's away
    # half-inning (bat_home_id='0', the _insert_event default) scores 0;
    # G1's home half-inning (bat_home_id='1') scores 1. Without a
    # bat_home filter both plays combine into one distribution; with
    # bat_home='1' only the scoring (home) play should appear, and with
    # bat_home='0' only the scoreless (away) play should appear.
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype, _season) "
            "VALUES ('G1', 'regular', '2021')"
        )
        _insert_event(cur, "G1", "0", "3", "2", bat_dest="0")  # away: scoreless
        _insert_event(cur, "G1", "0", "3", "23", bat_home_id="1", bat_dest="4")  # home: scores 1
    db_conn.commit()

    empty_zero = markov.BaseOutState(0, False, False, False)

    home_only = markov.estimate_outcome_distribution(db_conn, seasons=[2021], bat_home="1")
    away_only = markov.estimate_outcome_distribution(db_conn, seasons=[2021], bat_home="0")
    combined = markov.estimate_outcome_distribution(db_conn, seasons=[2021])

    assert list(home_only[empty_zero].keys()) == [markov.Outcome(markov.TERMINAL, 1)]
    assert list(away_only[empty_zero].keys()) == [markov.Outcome(markov.TERMINAL, 0)]
    assert len(combined[empty_zero]) == 2


def test_estimate_outcome_distribution_rejects_an_invalid_bat_home(db_conn):
    # A typo like 'home'/'away'/'2' would otherwise silently match zero
    # SQL rows (bat_home_id only ever contains '0'/'1') and return an
    # empty distribution instead of failing loudly -- fail fast on the
    # bad input itself, before any query runs.
    with pytest.raises(markov.MarkovError, match="bat_home"):
        markov.estimate_outcome_distribution(db_conn, seasons=[2021], bat_home="home")


def test_real_half_inning_runs_matches_hand_calculation(db_conn):
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype, _season) "
            "VALUES ('G1', 'regular', '2021'), ('G2', 'playoff', '2021')"
        )
        # G1, inning 1, away batting (bat_home_id='0'): two scoring plays
        # (3 runs total), then a double play completing the half-inning's
        # 3rd out -- real_half_inning_runs only counts half-innings that
        # actually reach 3 outs (see the walk-off test below for why).
        _insert_event(cur, "G1", "0", "0", "23", bat_dest="4")  # solo HR: 1 run
        _insert_event(
            cur, "G1", "0", "1", "21", b1="r1", b2="r2", bat_dest="2", r1_dest="4", r2_dest="4"
        )  # 2-run double, batter safe at 2nd
        _insert_event(cur, "G1", "1", "2", "2", bat_dest="0")  # double play: 3rd out
        # G1, inning 1, home batting (bat_home_id='1'): three separate outs,
        # no runs.
        _insert_event(cur, "G1", "0", "1", "3", bat_home_id="1", bat_dest="0")
        _insert_event(cur, "G1", "1", "1", "3", bat_home_id="1", bat_dest="0")
        _insert_event(cur, "G1", "2", "1", "3", bat_home_id="1", bat_dest="0")
        # G2 (playoff): would add a run if not excluded by the gametype filter.
        _insert_event(cur, "G2", "0", "0", "23", bat_dest="4")
    db_conn.commit()

    totals = markov.real_half_inning_runs(db_conn, seasons=[2021])

    assert sorted(totals) == [0, 3]


def test_real_half_inning_runs_excludes_a_walk_off_truncated_half_inning(db_conn):
    # A home half-inning that ends on the winning run (a real walk-off) never
    # records a 3rd out -- the game simply stops. simulate_half_inning always
    # walks a half-inning to TERMINAL (3 outs), so a truncated real
    # half-inning like this isn't an observation of the same quantity and
    # would bias the calibration comparison if counted; it must be excluded.
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype, _season) "
            "VALUES ('G1', 'regular', '2021')"
        )
        _insert_event(cur, "G1", "0", "1", "3", inn_ct="9", bat_home_id="1", bat_dest="0")
        _insert_event(
            cur,
            "G1",
            "1",
            "1",
            "21",
            inn_ct="9",
            bat_home_id="1",
            b1="r1",
            b2="r2",
            bat_dest="2",
            r1_dest="4",
            r2_dest="4",
        )  # walk-off 2-run double; game ends here, only 1 out ever recorded
    db_conn.commit()

    totals = markov.real_half_inning_runs(db_conn, seasons=[2021])

    assert totals == []


def test_real_half_inning_runs_returns_empty_when_tables_missing(db_conn):
    _reset(db_conn)
    assert markov.real_half_inning_runs(db_conn, seasons=[2021]) == []


def test_real_game_scores_matches_hand_calculation(db_conn):
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype, _season, vruns, hruns) "
            "VALUES ('G1', 'regular', '2021', '4', '2'), ('G2', 'playoff', '2021', '9', '9')"
        )
        # G1 plays across 2 innings, no runs recorded via events (the
        # events here only exist to establish which innings were played
        # -- the score itself comes from gameinfo's own vruns/hruns).
        _insert_event(cur, "G1", "0", "1", "3", inn_ct="1", bat_dest="0")
        _insert_event(cur, "G1", "0", "1", "3", inn_ct="2", bat_dest="0")
        # G2 (playoff): would be included if not excluded by the gametype filter.
        _insert_event(cur, "G2", "0", "1", "3", inn_ct="1", bat_dest="0")
    db_conn.commit()

    scores = markov.real_game_scores(db_conn, seasons=[2021])

    assert scores == [markov.GameResult(away_runs=4, home_runs=2, innings=2)]


def test_real_game_scores_returns_empty_when_tables_missing(db_conn):
    _reset(db_conn)
    assert markov.real_game_scores(db_conn, seasons=[2021]) == []


def test_estimate_matchup_distribution_filters_to_the_batting_team(db_conn):
    # NYA202104010: ATL (away) hits a solo HR; NYA (home) makes three
    # outs with no runs. A batting_team='ATL' matchup must see only the
    # HR; the unfiltered league distribution sees both outcomes.
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    _ensure_matchup_columns(db_conn)
    gid = "NYA202104010"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo "
            "(gid, gametype, _season, visteam, hometeam) "
            "VALUES (%s, 'regular', '2021', 'ATL', 'NYA')",
            (gid,),
        )
        _insert_event(cur, gid, "0", "3", "23", bat_dest="4", resp_pit_id="nyap001")
        _insert_event(cur, gid, "0", "3", "2", bat_home_id="1", bat_dest="0", resp_pit_id="atlp001")
    db_conn.commit()

    empty_zero = markov.BaseOutState(0, False, False, False)
    league = markov.estimate_outcome_distribution(db_conn, seasons=[2021])
    atl = markov.estimate_matchup_distribution(
        db_conn, seasons=[2021], batting_team="ATL", pitching_team="NYA", prior_pa=1
    )

    assert len(league[empty_zero]) == 2
    # prior_pa=1 and n=1 → even mix would appear if we used the league
    # prior heavily; with prior_pa=1 the ATL HR dominates. Check the HR
    # outcome is the majority, and the scoreless NYA play is the minority.
    atl_hr = atl[empty_zero][markov.Outcome(markov.TERMINAL, 1)]
    atl_out = atl[empty_zero][markov.Outcome(markov.TERMINAL, 0)]
    assert atl_hr > atl_out


def test_estimate_matchup_distribution_excludes_the_target_game(db_conn):
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    _ensure_matchup_columns(db_conn)
    prior = "NYA202104010"
    target = "NYA202104020"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo "
            "(gid, gametype, _season, visteam, hometeam, date) VALUES "
            "(%s, 'regular', '2021', 'ATL', 'NYA', '20210401'), "
            "(%s, 'regular', '2021', 'ATL', 'NYA', '20210402')",
            (prior, target),
        )
        _insert_event(cur, prior, "0", "3", "23", bat_dest="4")
        _insert_event(cur, target, "0", "3", "2", bat_dest="0")
    db_conn.commit()

    empty_zero = markov.BaseOutState(0, False, False, False)
    leaked = markov.estimate_matchup_distribution(
        db_conn, seasons=[2021], batting_team="ATL", prior_pa=1
    )
    pit = markov.estimate_matchup_distribution(
        db_conn,
        seasons=[2021],
        batting_team="ATL",
        exclude_game_id=target,
        prior_pa=1,
    )
    as_of = markov.estimate_matchup_distribution(
        db_conn,
        seasons=[2021],
        batting_team="ATL",
        before_date=date(2021, 4, 2),
        prior_pa=1,
    )

    # With both games, ATL has a HR and a scoreless play. Excluding the
    # target (or cutting off before it) leaves only the prior HR, so the
    # scoreless outcome's weight must drop.
    assert leaked[empty_zero][markov.Outcome(markov.TERMINAL, 0)] > pit[empty_zero].get(
        markov.Outcome(markov.TERMINAL, 0), 0
    )
    assert pit[empty_zero][markov.Outcome(markov.TERMINAL, 1)] == pytest.approx(
        as_of[empty_zero][markov.Outcome(markov.TERMINAL, 1)]
    )


def test_estimate_matchup_distribution_league_prior_excludes_the_target_game(db_conn):
    # The matchup sample for the target day is only the prior HR. If the
    # league prior still included the target's scoreless play, shrink
    # (n=1, M=1) would keep a 25% mass on 0 runs. A cutoff-correct prior
    # is HR-only, so the mix is 100% the HR.
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    _ensure_matchup_columns(db_conn)
    prior = "NYA202104010"
    target = "NYA202104020"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo "
            "(gid, gametype, _season, visteam, hometeam) VALUES "
            "(%s, 'regular', '2021', 'ATL', 'NYA'), "
            "(%s, 'regular', '2021', 'ATL', 'NYA')",
            (prior, target),
        )
        _insert_event(cur, prior, "0", "3", "23", bat_dest="4")
        _insert_event(cur, target, "0", "3", "2", bat_dest="0")
    db_conn.commit()

    empty_zero = markov.BaseOutState(0, False, False, False)
    pit = markov.estimate_matchup_distribution(
        db_conn,
        seasons=[2021],
        batting_team="ATL",
        exclude_game_id=target,
        prior_pa=1,
    )
    assert list(pit[empty_zero]) == [markov.Outcome(markov.TERMINAL, 1)]
    assert pit[empty_zero][markov.Outcome(markov.TERMINAL, 1)] == pytest.approx(1.0)


def test_estimate_matchup_distribution_unknown_team_returns_league(db_conn):
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    _ensure_matchup_columns(db_conn)
    gid = "NYA202104010"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo "
            "(gid, gametype, _season, visteam, hometeam) "
            "VALUES (%s, 'regular', '2021', 'ATL', 'NYA')",
            (gid,),
        )
        _insert_event(cur, gid, "0", "3", "23", bat_dest="4")
    db_conn.commit()

    league = markov.estimate_outcome_distribution(db_conn, seasons=[2021])
    fallback = markov.estimate_matchup_distribution(db_conn, seasons=[2021], batting_team="XXX")
    empty_zero = markov.BaseOutState(0, False, False, False)
    assert fallback[empty_zero] == league[empty_zero]


def test_estimate_matchup_distribution_returns_empty_when_tables_missing(db_conn):
    _reset(db_conn)
    assert markov.estimate_matchup_distribution(db_conn, seasons=[2021]) == {}


def test_estimate_matchup_distribution_rejects_a_bad_bat_home(db_conn):
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    _ensure_matchup_columns(db_conn)
    with pytest.raises(markov.MarkovError):
        markov.estimate_matchup_distribution(db_conn, seasons=[2021], bat_home="home")
    with pytest.raises(markov.MarkovError):
        markov.fetch_matchup_transition_counts(db_conn, [2021], bat_home="away")


def test_estimate_matchup_distribution_scopes_to_one_batting_side(db_conn):
    # One game: ATL (away, bat_home '0') hits a HR; NYA (home, bat_home
    # '1') makes an out. bat_home='0' must see only the HR outcome,
    # bat_home='1' only the out -- the two half-innings do not mix.
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    _ensure_matchup_columns(db_conn)
    gid = "NYA202104010"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo "
            "(gid, gametype, _season, visteam, hometeam, date) "
            "VALUES (%s, 'regular', '2021', 'ATL', 'NYA', '20210401')",
            (gid,),
        )
        _insert_event(cur, gid, "0", "3", "23", bat_home_id="0", bat_dest="4")
        _insert_event(cur, gid, "0", "3", "2", bat_home_id="1", bat_dest="0")
    db_conn.commit()

    empty_zero = markov.BaseOutState(0, False, False, False)
    away = markov.estimate_matchup_distribution(db_conn, seasons=[2021], bat_home="0", prior_pa=1)
    home = markov.estimate_matchup_distribution(db_conn, seasons=[2021], bat_home="1", prior_pa=1)
    assert list(away[empty_zero]) == [markov.Outcome(markov.TERMINAL, 1)]
    assert list(home[empty_zero]) == [markov.Outcome(markov.TERMINAL, 0)]


def test_estimate_matchup_distribution_backs_off_to_team_when_pitcher_sample_is_thin(db_conn):
    # ATL vs NYA: pitcher nyap001 faced ATL once (a HR). With
    # pitcher_min_pa=5 that one-PA sample is dropped and the estimate
    # falls back to the ATL-vs-NYA team matchup, which also includes a
    # scoreless play thrown by a different pitcher.
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    _ensure_matchup_columns(db_conn)
    gid = "NYA202104010"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo "
            "(gid, gametype, _season, visteam, hometeam, date) "
            "VALUES (%s, 'regular', '2021', 'ATL', 'NYA', '20210401')",
            (gid,),
        )
        _insert_event(
            cur, gid, "0", "3", "23", bat_home_id="0", bat_dest="4", resp_pit_id="nyap001"
        )
        _insert_event(cur, gid, "0", "3", "2", bat_home_id="0", bat_dest="0", resp_pit_id="nyap002")
    db_conn.commit()

    empty_zero = markov.BaseOutState(0, False, False, False)
    thin = markov.estimate_matchup_distribution(
        db_conn,
        seasons=[2021],
        batting_team="ATL",
        pitching_team="NYA",
        pit_id="nyap001",
        pitcher_min_pa=5,
        prior_pa=1,
    )
    # Backed off to the team matchup -> the scoreless play is now in the
    # sample, so a 0-run outcome carries real weight.
    assert thin[empty_zero].get(markov.Outcome(markov.TERMINAL, 0), 0) > 0


def test_fetch_matchup_transition_counts_rejects_empty_seasons(db_conn):
    """fetch_matchup_transition_counts must validate the seasons argument."""
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    _ensure_matchup_columns(db_conn)
    with pytest.raises(ValueError, match="seasons must not be empty"):
        markov.fetch_matchup_transition_counts(db_conn, [])
