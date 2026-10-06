"""meta.refresh_raw_profile() against real PostgreSQL: exact counts, season and
load-time ranges, a table without those columns, a dropped table, and single-table refresh."""

import json
import uuid

import pytest


@pytest.fixture
def raw_tables(db_conn):
    suffix = uuid.uuid4().hex[:8]
    seasoned = f"zz_prof_a_{suffix}"
    plain = f"zz_prof_b_{suffix}"
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE TABLE raw.{seasoned} (x text, _season text, _loaded_at timestamptz)")
        cur.execute(f"CREATE TABLE raw.{plain} (x text)")
        cur.execute(
            f"INSERT INTO raw.{seasoned} VALUES "
            "('a','1999','2026-01-01'), ('b','2003','2026-02-01'), ('c','2001','2026-03-01')"
        )
        cur.execute(f"INSERT INTO raw.{plain} VALUES ('only')")
    db_conn.commit()
    yield seasoned, plain
    with db_conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS raw.{seasoned}, raw.{plain}")
        cur.execute("DELETE FROM meta.raw_profile WHERE table_name LIKE 'zz_prof_%'")
    db_conn.commit()


def _row(db_conn, name):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT row_count, first_season, last_season, first_loaded_at::date::text, "
            "last_loaded_at::date::text FROM meta.raw_profile WHERE table_name = %s",
            (name,),
        )
        return cur.fetchone()


def test_profile_counts_seasons_and_load_times(db_conn, raw_tables):
    seasoned, plain = raw_tables
    with db_conn.cursor() as cur:
        cur.execute("SELECT meta.refresh_raw_profile()")
    db_conn.commit()
    assert _row(db_conn, seasoned) == (3, "1999", "2003", "2026-01-01", "2026-03-01")
    assert _row(db_conn, plain) == (1, None, None, None, None)


def test_single_table_refresh_touches_only_that_table(db_conn, raw_tables):
    seasoned, plain = raw_tables
    with db_conn.cursor() as cur:
        cur.execute("SELECT meta.refresh_raw_profile()")
        cur.execute(f"INSERT INTO raw.{plain} VALUES ('two')")
        cur.execute(f"INSERT INTO raw.{seasoned} VALUES ('d','2010','2026-04-01')")
        cur.execute("SELECT meta.refresh_raw_profile(%s)", (plain,))
        (written,) = cur.fetchone()
    db_conn.commit()
    assert written == 1
    assert _row(db_conn, plain)[0] == 2
    assert _row(db_conn, seasoned)[0] == 3  # not refreshed


def test_dropped_table_leaves_the_profile(db_conn, raw_tables):
    seasoned, plain = raw_tables
    with db_conn.cursor() as cur:
        cur.execute("SELECT meta.refresh_raw_profile()")
        cur.execute(f"DROP TABLE raw.{plain}")
        cur.execute("SELECT meta.refresh_raw_profile()")
    db_conn.commit()
    assert _row(db_conn, plain) is None
    assert _row(db_conn, seasoned) is not None


def test_empty_table_has_zero_rows_and_no_ranges(db_conn, raw_tables):
    seasoned, _ = raw_tables
    with db_conn.cursor() as cur:
        cur.execute(f"DELETE FROM raw.{seasoned}")
        cur.execute("SELECT meta.refresh_raw_profile(%s)", (seasoned,))
    db_conn.commit()
    assert _row(db_conn, seasoned) == (0, None, None, None, None)


def test_data_date_parses_every_known_form_and_rejects_the_rest(db_conn):
    cases = {
        "2008-03-27": "2008-03-27",
        "2008-03-27T01:56:00Z": "2008-03-27",
        "1871/05/16": "1871-05-16",
        "18990727": "1899-07-27",
        "18770428.0": "1877-04-28",
        "1790272860": "2026-09-24",
        "2000-13-45": None,
        "20000231": None,
        "hello": None,
        "": None,
        "99999999": None,
    }
    with db_conn.cursor() as cur:
        for text, expected in cases.items():
            cur.execute("SELECT meta.data_date(%s)::text", (text,))
            assert cur.fetchone()[0] == expected, text


def _profile_one(db_conn, name, columns, values, declared):
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE TABLE raw.{name} ({columns})")
        cur.execute(f"INSERT INTO raw.{name} VALUES {values}")
        cur.execute("SELECT meta.refresh_raw_profile(%s, %s::jsonb)", (name, json.dumps(declared)))
        cur.execute(
            "SELECT date_column, first_data_date::text, last_data_date::text, date_not_parsed "
            "FROM meta.raw_profile WHERE table_name = %s",
            (name,),
        )
        row = cur.fetchone()
        cur.execute(f"DROP TABLE raw.{name}")
        cur.execute("DELETE FROM meta.raw_profile WHERE table_name = %s", (name,))
    db_conn.commit()
    return row


def test_profile_records_the_declared_date_column(db_conn):
    name = f"zz_prof_d_{uuid.uuid4().hex[:8]}"
    values = "('19990412'), ('20010930'), ('20000101'), ('oops'), (NULL)"
    row = _profile_one(db_conn, name, "d text", values, {name: "d"})
    assert row == ("d", "1999-04-12", "2001-09-30", 1)


def test_a_declared_column_that_does_not_exist_is_recorded_as_none(db_conn):
    name = f"zz_prof_e_{uuid.uuid4().hex[:8]}"
    row = _profile_one(db_conn, name, "d text", "('19990412')", {name: "nope"})
    assert row == (None, None, None, None)
