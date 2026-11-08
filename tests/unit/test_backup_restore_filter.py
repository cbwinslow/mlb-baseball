"""Pure text-handling tests for backup.restore()'s dump preprocessing.

pg_dump 17+ writes `SET transaction_timeout = 0`, a GUC that only exists on a
PostgreSQL 17+ server. Restoring such a dump into the PostgreSQL 16 service CI
uses aborted on that line ("unrecognized configuration parameter") because
psql runs with ON_ERROR_STOP. The filter that drops unsupported session
settings is pure line handling, so it is tested here without a database; the
end-to-end proof that a restore now succeeds is
tests/integration/test_backup.py::test_restore_tolerates_newer_client_settings.
"""

from mlb_baseball import backup


def _dump(tmp_path, text):
    path = tmp_path / "dump.sql"
    path.write_text(text)
    return path


def test_drops_transaction_timeout_in_any_spacing_or_case(tmp_path):
    dump = _dump(
        tmp_path,
        "SET transaction_timeout = 0;\n"
        "SET TRANSACTION_TIMEOUT=0;\n"
        "SET statement_timeout = 0;\n"
        "SELECT 1;\n",
    )

    assert list(backup._restorable_lines(dump)) == [
        "SET statement_timeout = 0;\n",
        "SELECT 1;\n",
    ]


def test_keeps_other_session_settings_and_mentions_of_the_dropped_one(tmp_path):
    dump = _dump(
        tmp_path,
        "-- SET transaction_timeout = 0;\n"
        "SET idle_in_transaction_session_timeout = 0;\n"
        "SET client_encoding = 'UTF8';\n",
    )

    assert list(backup._restorable_lines(dump)) == [
        "-- SET transaction_timeout = 0;\n",
        "SET idle_in_transaction_session_timeout = 0;\n",
        "SET client_encoding = 'UTF8';\n",
    ]
