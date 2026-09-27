"""The Retrosheet tie-out runner against a small, consistent set of hand-built raw
tables in the disposable test database (season-total level).

Real PostgreSQL, because the queries and the read-only connection are the thing
under test. The fixture describes three 2019 games (two regular season, one
postseason) that every source agrees on, plus one 1930 box score that no other
source covers.
"""

import pytest

from mlb_baseball import tieout_run
from tests.conftest import TEST_DATABASE_URL

TABLES = {
    "raw.retrosheet_event": (
        "game_id text, event_id text, event_cd text, bat_event_fl text, "
        "event_runs_ct text, _season text, _scope text"
    ),
    "raw.retrosheet_plays": (
        "gid text, pa text, k text, walk text, hr text, runs text, _season text"
    ),
    "raw.retrosheet_batting": (
        "gid text, id text, stattype text, b_pa text, b_k text, b_w text, b_hr text, "
        "b_r text, _season text"
    ),
    "raw.retrosheet_gameinfo": "gid text, vruns text, hruns text, _season text",
    "raw.retrosheet_gamelog": (
        "v_homeruns text, h_homeruns text, v_strikeouts text, h_strikeouts text, "
        "v_walks text, h_walks text, v_score text, h_score text, _season text"
    ),
    "raw.retrosheet_gamelog_post": (
        "date text, v_homeruns text, h_homeruns text, v_strikeouts text, h_strikeouts text, "
        "v_walks text, h_walks text, v_score text, h_score text"
    ),
    "raw.retrosheet_box_game": (
        "game_id text, _season text, _scope text, linescore_away_runs text, "
        "linescore_home_runs text"
    ),
    "raw.retrosheet_box_batting": "game_id text, _scope text, hr text, so text, bb text",
}


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

        # event_id 1.. per game. A = regular, B = regular, C = postseason.
        events = [
            # game A: strikeout, walk, home run (1 run), a stolen base (not a batter event)
            ("ATL201904010", "1", "3", "T", "0", "2019", "pbp"),
            ("ATL201904010", "2", "14", "T", "0", "2019", "pbp"),
            ("ATL201904010", "3", "23", "T", "1", "2019", "pbp"),
            ("ATL201904010", "4", "4", "F", "0", "2019", "pbp"),
            # game B: single, out
            ("BOS201904020", "1", "20", "T", "0", "2019", "pbp"),
            ("BOS201904020", "2", "2", "T", "0", "2019", "pbp"),
            # game C (postseason): strikeout, home run (1 run)
            ("HOU201910120", "1", "3", "T", "0", "2019", "postseason"),
            ("HOU201910120", "2", "23", "T", "1", "2019", "postseason"),
            # a Negro-League-style duplicate copy of game B's first event (register E2)
            ("BOS201904020", "1", "20", "T", "0", "2019", "negro_league"),
        ]
        _insert(cur, "raw.retrosheet_event", events)

        plays = [
            ("ATL201904010", "1", "1", "0", "0", "0", "2019"),
            ("ATL201904010", "1", "0", "1", "0", "0", "2019"),
            ("ATL201904010", "1", "0", "0", "1", "1", "2019"),
            ("ATL201904010", "0", "0", "0", "0", "0", "2019"),
            ("BOS201904020", "1", "0", "0", "0", "0", "2019"),
            ("BOS201904020", "1", "0", "0", "0", "0", "2019"),
            ("HOU201910120", "1", "1", "0", "0", "0", "2019"),
            ("HOU201910120", "1", "0", "0", "1", "1", "2019"),
        ]
        _insert(cur, "raw.retrosheet_plays", plays)

        batting = [
            ("ATL201904010", "aaaaa001", "value", "1", "1", "0", "0", "0", "2019"),
            ("ATL201904010", "bbbbb001", "value", "1", "0", "1", "0", "0", "2019"),
            ("ATL201904010", "ccccc001", "value", "1", "0", "0", "1", "1", "2019"),
            # an 'official' variant of the same player-game must not be counted
            ("ATL201904010", "aaaaa001", "official", "1", "9", "9", "9", "9", "2019"),
            ("BOS201904020", "ddddd001", "value", "2", "0", "0", "0", "0", "2019"),
            ("HOU201910120", "eeeee001", "value", "2", "1", "0", "1", "1", "2019"),
        ]
        _insert(cur, "raw.retrosheet_batting", batting)

        _insert(
            cur,
            "raw.retrosheet_gameinfo",
            [
                ("ATL201904010", "0", "1", "2019"),
                ("BOS201904020", "0", "0", "2019"),
                ("HOU201910120", "1", "0", "2019"),
            ],
        )
        _insert(
            cur,
            "raw.retrosheet_gamelog",
            [
                # regular season only: games A and B
                ("0", "1", "1", "0", "0", "1", "0", "1", "2019"),
                ("0", "0", "0", "0", "0", "0", "0", "0", "2019"),
            ],
        )
        _insert(
            cur,
            "raw.retrosheet_gamelog_post",
            [("20191012", "1", "0", "1", "0", "0", "0", "1", "0")],
        )

        # a 1930 box score no other source covers
        _insert(cur, "raw.retrosheet_box_game", [("XXX193005010", "1930", "na", "3", "2")])
        _insert(cur, "raw.retrosheet_box_batting", [("XXX193005010", "na", "1", "2", "1")])
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
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE raw.retrosheet_batting SET b_k = '2' "
            "WHERE gid = 'HOU201910120' AND stattype = 'value'"
        )
    db_conn.commit()

    code, text = _run(db_conn=db_conn, lo=2019, hi=2019)

    assert code == 1, text
    assert "Retrosheet tie-out FAILED" in text
    assert "season 2019 k: event 2 vs csv_batting 3" in text


def test_a_game_log_difference_that_is_not_the_postseason_total_fails(db_conn, raw_tables):
    with db_conn.cursor() as cur:
        cur.execute("UPDATE raw.retrosheet_gamelog SET v_homeruns = '3' WHERE v_score = '0'")
    db_conn.commit()

    code, text = _run(db_conn=db_conn, lo=2019, hi=2019)

    assert code == 1, text
    assert "FAIL" in text


def test_a_stale_register_entry_fails_when_the_postseason_log_predicts_a_gap_that_is_absent(
    db_conn, raw_tables
):
    # Make the regular game log include the postseason home run (game B gets it),
    # so event and game log agree on home runs while the post-season log still
    # says the postseason had one: the register entry predicts a gap that is gone.
    with db_conn.cursor() as cur:
        cur.execute("UPDATE raw.retrosheet_gamelog SET v_homeruns = '1' WHERE h_score = '0'")
    db_conn.commit()

    code, text = _run(db_conn=db_conn, lo=2019, hi=2019)

    assert code == 1, text
    assert "stale register entry" in text


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
    _run(db_conn=db_conn, lo=1900, hi=2025)
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
