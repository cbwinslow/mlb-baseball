from unittest.mock import MagicMock, patch

import psycopg
import pytest

from mlb_baseball.reap_test_databases import (
    find_orphaned_test_databases,
    reap_orphaned_test_databases,
)


def test_finds_databases_matching_pattern_with_no_active_connections():
    cur = MagicMock()
    cur.execute.return_value = None
    cur.fetchall.return_value = [("mlb_test_0123456789ab",), ("mlb_test_cdef01234567",)]

    result = find_orphaned_test_databases(cur)

    assert result == ["mlb_test_0123456789ab", "mlb_test_cdef01234567"]
    (query, params), _ = cur.execute.call_args
    assert "~ %s" in query
    assert "^mlb_test_[0-9a-f]{12}$" in params


def test_reap_rejects_non_test_dsn():
    with pytest.raises(
        RuntimeError, match="Refusing to run test database reaper against non-test DSN"
    ):
        reap_orphaned_test_databases("postgresql:///mlb")


@patch("mlb_baseball.reap_test_databases.time.sleep")
@patch("mlb_baseball.reap_test_databases.psycopg.connect")
def test_reap_skips_databases_that_gain_connections_between_passes(mock_connect, mock_sleep):
    """A database appearing in first pass but not second pass (someone
    connected to it) must NOT be dropped."""
    mock_conn = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall.side_effect = [
        [("mlb_test_0123456789ab",), ("mlb_test_cdef01234567",)],  # first pass
        [("mlb_test_0123456789ab",)],  # second pass
    ]

    result = reap_orphaned_test_databases("postgresql:///mlb_test")

    assert result == ["mlb_test_0123456789ab"]
    drop_calls = [c for c in mock_cursor.execute.call_args_list if "DROP DATABASE" in str(c)]
    assert len(drop_calls) == 1


@patch("mlb_baseball.reap_test_databases.time.sleep")
@patch("mlb_baseball.reap_test_databases.psycopg.connect")
def test_reap_drops_databases_in_both_passes(mock_connect, mock_sleep):
    """Databases appearing in both passes are orphaned and must be dropped."""
    mock_conn = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall.side_effect = [
        [("mlb_test_0123456789ab",), ("mlb_test_cdef01234567",)],  # first pass
        [("mlb_test_0123456789ab",), ("mlb_test_cdef01234567",)],  # second pass
    ]

    result = reap_orphaned_test_databases("postgresql:///mlb_test")

    assert result == ["mlb_test_0123456789ab", "mlb_test_cdef01234567"]
    drop_calls = [c for c in mock_cursor.execute.call_args_list if "DROP DATABASE" in str(c)]
    assert len(drop_calls) == 2


@patch("mlb_baseball.reap_test_databases.time.sleep")
@patch("mlb_baseball.reap_test_databases.psycopg.connect")
def test_reap_handles_object_in_use_gracefully(mock_connect, mock_sleep):
    """If a database is in use when DROP is executed, ignore ObjectInUse and continue."""
    mock_conn = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall.side_effect = [
        [("mlb_test_0123456789ab",), ("mlb_test_cdef01234567",)],
        [("mlb_test_0123456789ab",), ("mlb_test_cdef01234567",)],
    ]

    # First drop raises ObjectInUse, second succeeds
    mock_cursor.execute.side_effect = [
        None,
        None,
        psycopg.errors.ObjectInUse("database in use"),
        None,
    ]

    result = reap_orphaned_test_databases("postgresql:///mlb_test")
    assert result == ["mlb_test_cdef01234567"]


@patch("mlb_baseball.reap_test_databases.time.sleep")
@patch("mlb_baseball.reap_test_databases.psycopg.connect")
def test_reap_returns_empty_list_when_no_orphans_in_first_pass(mock_connect, mock_sleep):
    """If no orphaned databases exist in first pass, return empty and don't wait."""
    mock_conn = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall.return_value = []

    result = reap_orphaned_test_databases("postgresql:///mlb_test")

    assert result == []
    mock_sleep.assert_not_called()
