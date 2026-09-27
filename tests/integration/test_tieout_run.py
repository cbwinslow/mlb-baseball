"""The Retrosheet tie-out runner against a small, consistent set of hand-built raw
tables in the disposable test database (season, game and player-game levels).

Real PostgreSQL, because the queries and the read-only connection are the thing
under test. The fixture describes three 2019 games (two regular season, one
postseason) that every source agrees on, plus one 1930 box score that no other
source covers.
"""

import pytest

from mlb_baseball import tieout_run
from tests.conftest import TEST_DATABASE_URL

ALL_LEVELS = ("season", "game", "player_game")

TABLES = {
    "raw.retrosheet_event": (
        "game_id text, event_id text, event_cd text, bat_event_fl text, "
        "event_runs_ct text, bat_id text, resp_bat_id text, pit_id text, _season text, "
        "_scope text"
    ),
    "raw.retrosheet_plays": (
        "gid text, batter text, pa text, k text, walk text, hr text, runs text, _season text"
    ),
    "raw.retrosheet_batting": (
        "gid text, id text, stattype text, b_pa text, b_k text, b_w text, b_hr text, "
        "b_r text, _season text"
    ),
    "raw.retrosheet_gameinfo": "gid text, vruns text, hruns text, _season text",
    "raw.retrosheet_gamelog": (
        "date text, game_number text, h_team text, v_homeruns text, h_homeruns text, "
        "v_strikeouts text, h_strikeouts text, v_walks text, h_walks text, v_score text, "
        "h_score text, _season text"
    ),
    "raw.retrosheet_gamelog_post": (
        "date text, game_number text, h_team text, v_homeruns text, h_homeruns text, "
        "v_strikeouts text, h_strikeouts text, v_walks text, h_walks text, v_score text, "
        "h_score text"
    ),
    "raw.retrosheet_box_game": (
        "game_id text, _season text, _scope text, linescore_away_runs text, "
        "linescore_home_runs text"
    ),
    "raw.retrosheet_box_batting": "game_id text, _scope text, id text, hr text, so text, bb text",
    "raw.retrosheet_roster": "player_id text, _season text",
    "raw.retrosheet_allplayers": "id text, _season text",
}

A, B, C = "ATL201904010", "BOS201904020", "HOU201910120"  # A, B regular season; C postseason


def _insert(cur, table, rows):
    width = len(rows[0])
    cur.executemany(f"INSERT INTO {table} VALUES ({', '.join(['%s'] * width)})", rows)


@pytest.fixture
def raw_tables(db_conn, drop_tables_after):
    with db_conn.cursor() as cur:
        for table, columns in TABLES.items():
            drop_tables_after(table)
            cur.execute(f"DROP TABLE IF EXISTS {table}")
            cur.execute(f"CREATE TABLE {table} ({columns})")

        P = "pppp0001"  # the pitcher in every event
        events = [
            # game A: strikeout, walk, home run (1 run), a stolen base (not a batter event).
            # The home run is a mid-plate-appearance substitution: ccsub001 is literally
            # at the plate (bat_id) but ccccc001 is the responsible batter Retrosheet
            # credits the result to (resp_bat_id), matching the CSV product's `batter`
            # (ccccc001, see the `plays`/`batting` fixtures below) -- reproduces the real
            # mechanism behind the ~250 false player_game failures a real run found
            # (openspec/changes/raw-source-tieout/results-2015-2025.md).
            (A, "1", "3", "T", "0", "aaaaa001", "aaaaa001", P, "2019", "pbp"),
            (A, "2", "14", "T", "0", "bbbbb001", "bbbbb001", P, "2019", "pbp"),
            (A, "3", "23", "T", "1", "ccsub001", "ccccc001", P, "2019", "pbp"),
            (A, "4", "4", "F", "0", "ccccc001", "ccccc001", P, "2019", "pbp"),
            # game B: single, out
            (B, "1", "20", "T", "0", "ddddd001", "ddddd001", P, "2019", "pbp"),
            (B, "2", "2", "T", "0", "ddddd001", "ddddd001", P, "2019", "pbp"),
            # game C (postseason): strikeout, home run (1 run)
            (C, "1", "3", "T", "0", "eeeee001", "eeeee001", P, "2019", "postseason"),
            (C, "2", "23", "T", "1", "eeeee001", "eeeee001", P, "2019", "postseason"),
            # a Negro-League-style duplicate copy of game B's first event (register E2)
            (B, "1", "20", "T", "0", "ddddd001", "ddddd001", P, "2019", "negro_league"),
        ]
        _insert(cur, "raw.retrosheet_event", events)

        plays = [
            (A, "aaaaa001", "1", "1", "0", "0", "0", "2019"),
            (A, "bbbbb001", "1", "0", "1", "0", "0", "2019"),
            (A, "ccccc001", "1", "0", "0", "1", "1", "2019"),
            (A, "ccccc001", "0", "0", "0", "0", "0", "2019"),
            (B, "ddddd001", "1", "0", "0", "0", "0", "2019"),
            (B, "ddddd001", "1", "0", "0", "0", "0", "2019"),
            (C, "eeeee001", "1", "1", "0", "0", "0", "2019"),
            (C, "eeeee001", "1", "0", "0", "1", "1", "2019"),
        ]
        _insert(cur, "raw.retrosheet_plays", plays)

        batting = [
            (A, "aaaaa001", "value", "1", "1", "0", "0", "0", "2019"),
            (A, "bbbbb001", "value", "1", "0", "1", "0", "0", "2019"),
            (A, "ccccc001", "value", "1", "0", "0", "1", "1", "2019"),
            # an 'official' variant of the same player-game must not be counted
            (A, "aaaaa001", "official", "1", "9", "9", "9", "9", "2019"),
            (B, "ddddd001", "value", "2", "0", "0", "0", "0", "2019"),
            (C, "eeeee001", "value", "2", "1", "0", "1", "1", "2019"),
        ]
        _insert(cur, "raw.retrosheet_batting", batting)

        _insert(
            cur,
            "raw.retrosheet_gameinfo",
            [(A, "0", "1", "2019"), (B, "0", "0", "2019"), (C, "1", "0", "2019")],
        )
        _insert(
            cur,
            "raw.retrosheet_gamelog",
            [
                # regular season only: games A and B (home team, date, game number)
                ("20190401", "0", "ATL", "0", "1", "1", "0", "0", "1", "0", "1", "2019"),
                ("20190402", "0", "BOS", "0", "0", "0", "0", "0", "0", "0", "0", "2019"),
            ],
        )
        _insert(
            cur,
            "raw.retrosheet_gamelog_post",
            [("20191012", "0", "HOU", "1", "0", "1", "0", "0", "0", "1", "0")],
        )

        # a 1930 box score no other source covers
        _insert(cur, "raw.retrosheet_box_game", [("XXX193005010", "1930", "na", "3", "2")])
        _insert(
            cur, "raw.retrosheet_box_batting", [("XXX193005010", "na", "zzzzz001", "1", "2", "1")]
        )

        _insert(
            cur,
            "raw.retrosheet_roster",
            [
                (p, "2019")
                for p in ("aaaaa001", "bbbbb001", "ccccc001", "ccsub001", "ddddd001", "eeeee001")
            ],
        )
        _insert(cur, "raw.retrosheet_allplayers", [(P, "2019")])
    db_conn.commit()


def _run(dry_run=False, expect_db=None, levels=("season",), lo=2019, hi=2019, db_conn=None):
    lines: list[str] = []
    if expect_db is None:
        with db_conn.cursor() as cur:
            cur.execute("SELECT current_database()")
            expect_db = cur.fetchone()[0]
        db_conn.rollback()
    code = tieout_run.execute(
        url=TEST_DATABASE_URL,
        expect_db=expect_db,
        lo=lo,
        hi=hi,
        levels=list(levels),
        dry_run=dry_run,
        statement_timeout_ms=60_000,
        out=lines.append,
    )
    return code, "\n".join(lines)


def _update(db_conn, sql):
    with db_conn.cursor() as cur:
        cur.execute(sql)
    db_conn.commit()


# --- season totals ----------------------------------------------------------


def test_consistent_sources_pass_and_report_the_explained_postseason_gap(db_conn, raw_tables):
    code, text = _run(db_conn=db_conn, lo=1900, hi=2025)

    assert code == 0, text
    assert "Retrosheet tie-out PASSED" in text
    # event vs the regular-season game log differs by exactly the postseason game (E1)
    assert "explained by E1" in text
    # the 1930 box score is covered by no other source: never reported as a pass
    assert "not comparable: 1930 covered only by box" in text
    # the run says what it read
    assert "(read-only)" in text and "loaded season event" in text


def test_the_official_batting_variant_and_the_duplicate_event_are_not_double_counted(
    db_conn, raw_tables
):
    code, text = _run(db_conn=db_conn, lo=2019, hi=2019)

    # If 'official' rows or the duplicated event copy were counted, event vs
    # csv_batting and event vs csv_plays would disagree and the gate would fail.
    assert code == 0, text
    assert "FAIL" not in text


def test_a_planted_strikeout_difference_fails_the_gate(db_conn, raw_tables):
    _update(
        db_conn,
        f"UPDATE raw.retrosheet_batting SET b_k = '2' WHERE gid = '{C}' AND stattype = 'value'",
    )

    code, text = _run(db_conn=db_conn, lo=2019, hi=2019)

    assert code == 1, text
    assert "Retrosheet tie-out FAILED" in text
    assert "season 2019 k: event 2 vs csv_batting 3" in text


def test_a_game_log_difference_that_is_not_the_postseason_total_fails(db_conn, raw_tables):
    _update(db_conn, "UPDATE raw.retrosheet_gamelog SET v_homeruns = '3' WHERE v_score = '0'")

    code, text = _run(db_conn=db_conn, lo=2019, hi=2019)

    assert code == 1, text
    assert "FAIL" in text


def test_a_stale_register_entry_fails_when_the_postseason_log_predicts_a_gap_that_is_absent(
    db_conn, raw_tables
):
    # Make the regular game log include the postseason home run (game B gets it),
    # so event and game log agree on home runs while the post-season log still
    # says the postseason had one: the register entry predicts a gap that is gone.
    _update(db_conn, "UPDATE raw.retrosheet_gamelog SET v_homeruns = '1' WHERE h_score = '0'")

    code, text = _run(db_conn=db_conn, lo=2019, hi=2019)

    assert code == 1, text
    assert "stale register entry" in text


# --- game and player-game levels --------------------------------------------


def test_all_levels_pass_on_consistent_sources_and_explain_the_postseason_game(db_conn, raw_tables):
    code, text = _run(db_conn=db_conn, levels=ALL_LEVELS, lo=1900, hi=2025)

    assert code == 0, text
    assert "game level:" in text and "player_game level:" in text
    # at game level the postseason game is missing from the regular-season log (E1)
    assert "explained by E1: game 2019/HOU201910120" in text
    assert "every event batter and pitcher id 1900-2025 resolves" in text


def test_a_single_dropped_strikeout_is_reported_with_season_and_game(db_conn, raw_tables):
    _update(
        db_conn,
        f"UPDATE raw.retrosheet_plays SET k = '0' WHERE gid = '{A}' AND batter = 'aaaaa001' "
        "AND pa = '1'",
    )

    code, text = _run(db_conn=db_conn, levels=ALL_LEVELS)

    assert code == 1, text
    assert f"game 2019/{A} k: event 1 vs csv_plays 0" in text
    assert f"player_game 2019/{A}/aaaaa001 k: event 1 vs csv_plays 0" in text


def test_two_opposite_game_errors_cancel_in_the_season_total_but_are_both_reported(
    db_conn, raw_tables
):
    # csv_plays loses the strikeout in game A and gains one in game B: the season
    # total (2) still matches the events, so only the finer levels can see it.
    _update(
        db_conn,
        f"UPDATE raw.retrosheet_plays SET k = '0' WHERE gid = '{A}' AND batter = 'aaaaa001' "
        "AND pa = '1'",
    )
    _update(
        db_conn,
        f"UPDATE raw.retrosheet_plays SET k = '1' WHERE gid = '{B}' AND ctid = "
        f"(SELECT min(ctid) FROM raw.retrosheet_plays WHERE gid = '{B}')",
    )

    season_only_code, season_only_text = _run(db_conn=db_conn, levels=("season",))
    code, text = _run(db_conn=db_conn, levels=ALL_LEVELS)

    assert season_only_code == 0, season_only_text  # the season total alone is fooled
    assert code == 1, text
    assert f"game 2019/{A} k: event 1 vs csv_plays 0" in text
    assert f"game 2019/{B} k: event 0 vs csv_plays 1" in text


def test_a_mid_plate_appearance_substitution_is_credited_to_the_responsible_batter(
    db_conn, raw_tables
):
    """Game A's home run is bat_id=ccsub001 / resp_bat_id=ccccc001 (a substitute
    finishes the plate appearance; Retrosheet credits the result to the
    responsible batter). The CSV product already credits ccccc001. If the
    player-game comparison grouped by bat_id instead of resp_bat_id -- the real
    bug a production run found (results-2015-2025.md) -- this would report both
    ccsub001 (extra) and ccccc001 (missing) as mismatches; grouped correctly, it
    passes and nobody named ccsub001 appears in the identity check either."""
    code, text = _run(db_conn=db_conn, levels=ALL_LEVELS)

    assert code == 0, text
    assert "ccsub001" not in text
    assert f"player_game 2019/{A}/ccccc001" not in text


def test_crediting_the_substitute_instead_of_the_responsible_batter_fails(db_conn, raw_tables):
    """Same fixture, with resp_bat_id reverted to the substitute's own id --
    simulating the pre-fix behaviour of grouping by bat_id. Proves the check
    actually discriminates the two conventions rather than passing regardless."""
    _update(
        db_conn,
        f"UPDATE raw.retrosheet_event SET resp_bat_id = 'ccsub001' "
        f"WHERE game_id = '{A}' AND event_id = '3'",
    )

    code, text = _run(db_conn=db_conn, levels=ALL_LEVELS)

    assert code == 1, text
    assert f"player_game 2019/{A}/ccsub001 hr: event 1 vs csv_plays absent" in text
    # ccccc001 still has a key (its non-batter stolen-base event, event 4) so it
    # reads as a real 0-vs-1 mismatch rather than "absent".
    assert f"player_game 2019/{A}/ccccc001 hr: event 0 vs csv_plays 1" in text


def test_a_missing_roster_identifier_is_listed_with_season_and_example_game(db_conn, raw_tables):
    _update(db_conn, "DELETE FROM raw.retrosheet_roster WHERE player_id = 'bbbbb001'")

    code, text = _run(db_conn=db_conn, levels=ALL_LEVELS)

    assert code == 0, text  # a listed identifier is a finding to triage, not a source disagreement
    assert f"note: unresolved batter id 'bbbbb001' in 2019: 1 events, e.g. game {A}" in text


def test_a_player_missing_from_one_source_shows_as_absent(db_conn, raw_tables):
    _update(db_conn, "DELETE FROM raw.retrosheet_batting WHERE id = 'bbbbb001'")

    code, text = _run(db_conn=db_conn, levels=ALL_LEVELS)

    assert code == 1, text
    assert f"player_game 2019/{A}/bbbbb001 pa: event 1 vs csv_batting absent" in text


# --- safety and the entry point ---------------------------------------------


def test_the_gate_writes_nothing(db_conn, raw_tables):
    def snapshot():
        with db_conn.cursor() as cur:
            out = {}
            for table in TABLES:
                cur.execute(f"SELECT count(*) FROM {table}")
                out[table] = cur.fetchone()[0]
        db_conn.rollback()
        return out

    before = snapshot()
    _run(db_conn=db_conn, levels=ALL_LEVELS, lo=1900, hi=2025)
    assert snapshot() == before


def test_dry_run_prints_the_target_and_exits_zero_without_querying(db_conn, raw_tables):
    code, text = _run(dry_run=True, db_conn=db_conn)

    assert code == 0, text
    assert "target: database" in text and "(read-only)" in text
    assert "dry run" in text
    assert "loaded season" not in text


def test_the_wrong_database_name_is_refused_with_exit_two(db_conn, raw_tables):
    code, text = _run(expect_db="mlb", db_conn=db_conn)

    assert code == 2
    assert "expected 'mlb'" in text
    assert "loaded season" not in text
