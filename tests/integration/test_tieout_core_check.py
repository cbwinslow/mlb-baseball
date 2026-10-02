"""The Retrosheet tie-out gate's core.play/core.game completeness check (task 2.5).

Real PostgreSQL, using the migrated core schema plus a small hand-built raw
fixture. Three event games, all with a matching raw.retrosheet_gameinfo row: A
and B are wired into core.game/core.play correctly; C has never been conformed
into core.game at all (the audit's G7 gap -- an event game outside core.play's
population, reported as a note). The fixture also plants the task's other
defect, a dropped baserunning play (plate-appearance counts unaffected).

core.play's own UNIQUE(season, game_id, source, play_index) constraint
(migration 0006) already makes a literal duplicate row structurally
impossible to insert against a normally migrated database -- confirmed
directly (a `psycopg.errors.UniqueViolation` on the first attempt while
writing this file), not assumed. The keyed check's duplicate-counting branch
stays as defense-in-depth for a partial/inconsistent database state; it is not
exercised here for that reason.
"""

import psycopg
import pytest

from mlb_baseball import tieout_run
from tests.conftest import TEST_DATABASE_URL

# run_tieout always loads season totals first (they decide season coverage),
# even when only "core" is requested -- so every season source's table must
# exist with the right columns. The ones besides event/gameinfo stay empty:
# a source with no rows for 2019 makes that pair "not comparable", never a
# failure, and this file's fixture is only about the core check itself.
RAW_TABLES = {
    "raw.retrosheet_event": (
        "game_id text, event_id text, event_cd text, bat_event_fl text, "
        "event_runs_ct text, inn_ct text, bat_home_id text, event_tx text, "
        "away_score_ct text, home_score_ct text, bat_id text, pit_id text, "
        "_season text, _scope text"
    ),
    "raw.retrosheet_gameinfo": (
        "gid text, date text, vruns text, hruns text, gametype text, site text, "
        "daynight text, _season text"
    ),
    "raw.retrosheet_plays": (
        "gid text, pa text, k text, walk text, hr text, runs text, _season text"
    ),
    "raw.retrosheet_batting": (
        "gid text, id text, stattype text, b_pa text, b_k text, b_w text, b_hr text, "
        "b_r text, _season text"
    ),
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

A, B, C = "ATL201904010", "ATL201904020", "ATL201904030"  # C has no core.game row


def _insert(cur, table, rows):
    width = len(rows[0])
    cur.executemany(f"INSERT INTO {table} VALUES ({', '.join(['%s'] * width)})", rows)


@pytest.fixture
def core_fixture(db_conn, drop_tables_after):
    with db_conn.cursor() as cur:
        for table, columns in RAW_TABLES.items():
            drop_tables_after(table)
            cur.execute(f"DROP TABLE IF EXISTS {table}")
            cur.execute(f"CREATE TABLE {table} ({columns})")

        _insert(
            cur,
            "raw.retrosheet_event",
            [
                # game A: a strikeout (batter event) and a stolen base (baserunning,
                # not a batter event) -- the stolen base is the one that will be
                # dropped from core.play by one test without moving pa/k.
                (
                    A,
                    "1",
                    "3",
                    "T",
                    "0",
                    "1",
                    "1",
                    "K",
                    "0",
                    "0",
                    "aaaaa001",
                    "ppppp001",
                    "2019",
                    "pbp",
                ),
                (
                    A,
                    "2",
                    "4",
                    "F",
                    "0",
                    "1",
                    "1",
                    "SB2",
                    "0",
                    "0",
                    "aaaaa001",
                    "ppppp001",
                    "2019",
                    "pbp",
                ),
                # game B: one strikeout
                (
                    B,
                    "1",
                    "3",
                    "T",
                    "0",
                    "1",
                    "0",
                    "K",
                    "0",
                    "0",
                    "bbbbb001",
                    "ppppp001",
                    "2019",
                    "pbp",
                ),
                # game C: has both an event and a gameinfo row (so the ordinary
                # season/game totals agree) but conform has not built its
                # core.game row yet -- the audit's G7 condition, not "no gameinfo
                # row at all": that specific historical case is a different,
                # already-known population gap between event and gameinfo
                # (conform.py's Oct-1900 Pittsburgh-series comment) that needs its
                # own register entry once measured against real history (task
                # 4.1/4.2), not something this fixture should also trip.
                (
                    C,
                    "1",
                    "3",
                    "T",
                    "0",
                    "1",
                    "0",
                    "K",
                    "0",
                    "0",
                    "ccccc001",
                    "ppppp001",
                    "2019",
                    "pbp",
                ),
            ],
        )
        _insert(
            cur,
            "raw.retrosheet_gameinfo",
            [
                (A, "20190401", "0", "0", "regular", "ATL01", "N", "2019"),
                (B, "20190402", "0", "0", "regular", "ATL01", "N", "2019"),
                (C, "20190403", "0", "0", "regular", "ATL01", "N", "2019"),
            ],
        )

        cur.execute("DELETE FROM core.play")
        cur.execute("DELETE FROM core.game WHERE retro_game_id IN (%s, %s, %s)", (A, B, C))
        cur.execute(
            "INSERT INTO core.game (retro_game_id, season, game_date, away_score, home_score, "
            "game_type, site, day_night) VALUES "
            "(%s, 2019, '2019-04-01', 0, 0, 'regular', 'ATL01', 'N'), "
            "(%s, 2019, '2019-04-02', 0, 0, 'regular', 'ATL01', 'N') "
            "RETURNING id, retro_game_id",
            (A, B),
        )
        game_id = {retro_id: pk for pk, retro_id in cur.fetchall()}
        cur.execute(
            "INSERT INTO core.play (game_id, season, source, play_index, inning, half_inning, "
            "event_code, event_desc, away_score, home_score) VALUES "
            "(%s, 2019, 'retrosheet', 1, 1, 'bottom', '3', 'K', 0, 0), "
            "(%s, 2019, 'retrosheet', 2, 1, 'bottom', '4', 'SB2', 0, 0), "
            "(%s, 2019, 'retrosheet', 1, 1, 'top', '3', 'K', 0, 0)",
            (game_id[A], game_id[A], game_id[B]),
        )
    db_conn.commit()
    yield game_id
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM core.play WHERE game_id = ANY(%s)", (list(game_id.values()),))
        cur.execute("DELETE FROM core.game WHERE id = ANY(%s)", (list(game_id.values()),))
    db_conn.commit()


def _run(db_conn, levels=("core",), lo=2019, hi=2019):
    lines: list[str] = []
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
        dry_run=False,
        statement_timeout_ms=60_000,
        out=lines.append,
    )
    return code, "\n".join(lines)


def test_a_game_missing_from_core_notes_the_gap_and_fails_until_it_is_registered(
    db_conn, core_fixture
):
    # C has a raw.retrosheet_gameinfo row but no core.game row (conform has not
    # processed it -- audit G8, core.game incompleteness). The note names the
    # gap either way (audit G7 asks for visibility, not a guess at cause), but
    # the ordinary season/game-info-vs-core.game count and attribute checks
    # correctly still fail on it: design D3 requires a difference no register
    # entry explains to fail, and no fixture-specific entry exists for this
    # synthetic gap. A real occurrence gets a register entry once measured
    # against production (passmarks.md; play-engine's Oct-1900 example).
    code, text = _run(db_conn)

    assert code == 1, text
    assert "core completeness check" in text
    assert (
        "note: season 2019: 1 event game(s) have no core.game row and are excluded "
        f"from core.play (e.g. {C}); see audit finding G7" in text
    )
    assert f"gameinfo row(s) have no core.game row (e.g. {C})" in text
    assert "season 2019 g: gameinfo 3 vs core_game 2" in text


def test_a_dropped_baserunning_play_fails_even_though_plate_appearances_are_unchanged(
    db_conn, core_fixture
):
    game_id = core_fixture
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM core.play WHERE game_id = %s AND play_index = 2", (game_id[A],))
    db_conn.commit()

    code, text = _run(db_conn)

    assert code == 1, text
    # the plate-appearance-only comparison (event_core vs core_play) does not
    # see this at all -- only the full keyed comparison does.
    assert f"{A}#2" in text
    assert "missing from core.play" in text


def test_a_literal_duplicate_play_is_rejected_by_the_schema_itself(db_conn, core_fixture):
    # Documents the fact behind the module docstring: core.play's own
    # UNIQUE(season, game_id, source, play_index) constraint (migration 0006)
    # already makes this defect impossible to create, so the keyed check's
    # duplicate-counting branch cannot be exercised against a normally
    # migrated database -- it is defense-in-depth, not dead weight.
    game_id = core_fixture
    with (
        pytest.raises(psycopg.errors.UniqueViolation),
        db_conn.cursor() as cur,
    ):
        cur.execute(
            "INSERT INTO core.play (game_id, season, source, play_index, inning, half_inning, "
            "event_code, event_desc, away_score, home_score) VALUES "
            "(%s, 2019, 'retrosheet', 2, 1, 'bottom', '4', 'SB2', 0, 0)",
            (game_id[A],),
        )
    db_conn.rollback()


def test_a_mismatched_attribute_is_reported(db_conn, core_fixture):
    game_id = core_fixture
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE core.play SET inning = 9 WHERE game_id = %s AND play_index = 1", (game_id[A],)
        )
    db_conn.commit()

    code, text = _run(db_conn)

    assert code == 1, text
    assert "mismatched inning vs raw.retrosheet_event" in text


def test_a_gameinfo_row_missing_from_core_game_entirely_is_reported(db_conn, core_fixture):
    game_id = core_fixture
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM core.play WHERE game_id = %s", (game_id[B],))
        cur.execute("DELETE FROM core.game WHERE retro_game_id = %s", (B,))
    db_conn.commit()

    code, text = _run(db_conn)

    assert code == 1, text
    assert f"gameinfo row(s) have no core.game row (e.g. {B})" in text


def test_the_core_check_writes_nothing(db_conn, core_fixture):
    def snapshot():
        with db_conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM core.game")
            game_count = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM core.play")
            play_count = cur.fetchone()[0]
        db_conn.rollback()
        return game_count, play_count

    before = snapshot()
    _run(db_conn)
    assert snapshot() == before


def test_core_check_is_not_run_unless_requested(db_conn, core_fixture):
    code, text = _run(db_conn, levels=("season",))

    assert code == 0, text
    assert "core completeness check" not in text
