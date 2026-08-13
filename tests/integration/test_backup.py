"""Regression coverage for mlb_baseball.backup -- pg_dump/pg_restore
wrapper. Uses the real mlb_test database and the real installed pg_dump/
psql tools (no mocking the database or the external process, per this
project's testing conventions) but never touches the shared raw/core/
gold/meta schemas other tests depend on -- everything here operates on a
disposable schema this test file creates and drops itself.
"""

import os

import pytest

from mlb_baseball import backup

SCRATCH_SCHEMA = "backup_test_scratch"


@pytest.fixture
def database_url():
    # Set by tests/conftest.py's session fixture before any test runs --
    # read at test-run time, not import time, since the fixture hasn't
    # necessarily set it yet when this module is first imported.
    return os.environ["DATABASE_URL"]


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {SCRATCH_SCHEMA} CASCADE")
    db_conn.commit()


def _create_scratch_table_with_rows(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA {SCRATCH_SCHEMA}")
        cur.execute(f"CREATE TABLE {SCRATCH_SCHEMA}.widget (id integer PRIMARY KEY, name text)")
        cur.execute(
            f"INSERT INTO {SCRATCH_SCHEMA}.widget (id, name) VALUES (1, 'left-handed hammer')"
        )
    db_conn.commit()


def test_missing_tools_reports_nothing_when_tools_are_present():
    # This suite can't run at all without a real Postgres connection, and
    # pg_dump/psql are required to be on PATH for these tests to mean
    # anything -- if this fails, every other test in this file will too,
    # for the same underlying reason (see backup.INSTALL_HINT).
    assert backup.missing_tools() == []


def test_backup_writes_a_real_dump_file_containing_expected_content(
    db_conn, tmp_path, database_url
):
    _reset(db_conn)
    _create_scratch_table_with_rows(db_conn)

    output_path = backup.backup(database_url, tmp_path, schemas=[SCRATCH_SCHEMA])

    assert output_path.exists()
    content = output_path.read_text()
    assert "CREATE TABLE" in content
    assert "widget" in content
    assert "left-handed hammer" in content

    _reset(db_conn)


def test_backup_schema_only_excludes_row_data(db_conn, tmp_path, database_url):
    _reset(db_conn)
    _create_scratch_table_with_rows(db_conn)

    output_path = backup.backup(database_url, tmp_path, schemas=[SCRATCH_SCHEMA], schema_only=True)

    content = output_path.read_text()
    assert "CREATE TABLE" in content
    assert "left-handed hammer" not in content

    _reset(db_conn)


def test_backup_raises_clear_error_if_pg_dump_missing(tmp_path, monkeypatch, database_url):
    monkeypatch.setattr(backup, "missing_tools", lambda: ["pg_dump"])
    with pytest.raises(RuntimeError, match="pg_dump"):
        backup.backup(database_url, tmp_path)


def test_restore_refuses_without_explicit_confirmation(tmp_path, database_url):
    fake_dump = tmp_path / "fake.sql"
    fake_dump.write_text("SELECT 1;")
    with pytest.raises(RuntimeError, match="confirm=True"):
        backup.restore(database_url, fake_dump, confirm=False)


def test_restore_full_round_trip_recreates_dropped_data(db_conn, tmp_path, database_url):
    # The real proof a backup is worth anything: back it up, actually lose
    # the data, restore, confirm it's back -- not just "the tool ran".
    _reset(db_conn)
    _create_scratch_table_with_rows(db_conn)

    dump_path = backup.backup(database_url, tmp_path, schemas=[SCRATCH_SCHEMA])

    with db_conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA {SCRATCH_SCHEMA} CASCADE")
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (f"{SCRATCH_SCHEMA}.widget",))
        assert cur.fetchone()[0] is None  # confirm it's actually gone

    backup.restore(database_url, dump_path, confirm=True)

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT id, name FROM {SCRATCH_SCHEMA}.widget")
        rows = cur.fetchall()
    assert rows == [(1, "left-handed hammer")]

    _reset(db_conn)
