"""The Retrosheet tie-out gate's production schema check (task 2.6, design D6).

Real PostgreSQL. ``raw.retrosheet_roster`` (a real production table) is created
matching the pinned contract's actual columns
(``mlb_baseball.tieout_schema_contract.RAW_SCHEMA_CONTRACT``), then broken with
a dropped and an added column, to prove ``run_schema_check`` reads
``information_schema`` for real and reports exactly what changed. The contract
passed is a one-table restriction of the real pin, not the full ten-table
production contract -- a fixture only needs to prove the mechanism, not
recreate every raw table.
"""

from mlb_baseball import tieout_run
from mlb_baseball.tieout import Report
from mlb_baseball.tieout_schema_contract import RAW_SCHEMA_CONTRACT

ROSTER_CONTRACT = {"raw.retrosheet_roster": RAW_SCHEMA_CONTRACT["raw.retrosheet_roster"]}


def test_a_table_matching_its_pinned_columns_exactly_passes(db_conn, drop_tables_after):
    drop_tables_after("raw.retrosheet_roster")
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_roster")
        cur.execute(
            "CREATE TABLE raw.retrosheet_roster (player_id text, last_name text, "
            "first_name text, bats text, throws text, team_id text, position text, "
            "_season text, _loaded_at timestamptz)"
        )
    db_conn.commit()

    report = Report()
    tieout_run.run_schema_check(db_conn, report, lambda _line: None, contract=ROSTER_CONTRACT)

    assert report.problems == []


def test_a_missing_and_an_extra_column_are_both_reported(db_conn, drop_tables_after):
    drop_tables_after("raw.retrosheet_roster")
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_roster")
        # missing: throws, position (pinned but not created here)
        # extra: nickname (created here but not pinned)
        cur.execute(
            "CREATE TABLE raw.retrosheet_roster (player_id text, last_name text, "
            "first_name text, bats text, team_id text, _season text, "
            "_loaded_at timestamptz, nickname text)"
        )
    db_conn.commit()

    report = Report()
    tieout_run.run_schema_check(db_conn, report, lambda _line: None, contract=ROSTER_CONTRACT)

    assert len(report.problems) == 2
    assert any(
        "raw.retrosheet_roster is missing column(s) position, throws" in p for p in report.problems
    )
    assert any(
        "raw.retrosheet_roster has unexpected column(s) nickname" in p for p in report.problems
    )


def test_a_table_absent_entirely_is_reported(db_conn, drop_tables_after):
    drop_tables_after("raw.retrosheet_roster")
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_roster")
    db_conn.commit()

    report = Report()
    tieout_run.run_schema_check(db_conn, report, lambda _line: None, contract=ROSTER_CONTRACT)

    assert report.problems == [
        "schema contract: raw.retrosheet_roster does not exist in this database"
    ]


def test_the_schema_check_writes_nothing(db_conn, drop_tables_after):
    drop_tables_after("raw.retrosheet_roster")
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_roster")
        cur.execute("CREATE TABLE raw.retrosheet_roster (player_id text)")
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.retrosheet_roster")
        before = cur.fetchone()[0]
    db_conn.rollback()

    tieout_run.run_schema_check(db_conn, Report(), lambda _line: None, contract=ROSTER_CONTRACT)

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.retrosheet_roster")
        after = cur.fetchone()[0]
    db_conn.rollback()
    assert before == after == 0
