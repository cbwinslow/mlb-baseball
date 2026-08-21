from unittest.mock import MagicMock, patch

from mlb_baseball.reap_test_databases import (
    find_orphaned_test_databases,
    reap_orphaned_test_databases,
)


def test_finds_databases_matching_pattern_with_no_active_connections():
    cur = MagicMock()
    cur.execute.return_value = None
    cur.fetchall.return_value = [("mlb_test_abc123",), ("mlb_test_def456",)]

    result = find_orphaned_test_databases(cur)

    assert result == ["mlb_test_abc123", "mlb_test_def456"]
    (query, params), _ = cur.execute.call_args
    assert "mlb\\_test\\_%" in query or "mlb\\_test\\_%" in params


@patch("mlb_baseball.reap_test_databases.time.sleep")
@patch("mlb_baseball.reap_test_databases.psycopg.connect")
def test_reap_skips_databases_that_gain_connections_between_passes(mock_connect, mock_sleep):
    """A database appearing in first pass but not second pass (someone
    connected to it) must NOT be dropped."""
    # Setup mock connection and cursor
    mock_conn = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # First pass: mlb_test_orphan exists; mlb_test_gained_connection exists
    # Second pass: only mlb_test_orphan exists (mlb_test_gained_connection is gone)
    mock_cursor.fetchall.side_effect = [
        [("mlb_test_orphan",), ("mlb_test_gained_connection",)],  # first pass
        [("mlb_test_orphan",)],  # second pass
    ]

    result = reap_orphaned_test_databases("postgresql:///mlb_test")

    # Only mlb_test_orphan should be dropped (intersection logic)
    assert result == ["mlb_test_orphan"]
    # Verify DROP was only called once, for mlb_test_orphan
    drop_calls = [c for c in mock_cursor.execute.call_args_list if "DROP DATABASE" in str(c)]
    assert len(drop_calls) == 1


@patch("mlb_baseball.reap_test_databases.time.sleep")
@patch("mlb_baseball.reap_test_databases.psycopg.connect")
def test_reap_drops_databases_in_both_passes(mock_connect, mock_sleep):
    """Databases appearing in both passes are orphaned and must be dropped."""
    # Setup mock connection and cursor
    mock_conn = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # Both passes return the same orphaned databases
    mock_cursor.fetchall.side_effect = [
        [("mlb_test_orphan1",), ("mlb_test_orphan2",)],  # first pass
        [("mlb_test_orphan1",), ("mlb_test_orphan2",)],  # second pass
    ]

    result = reap_orphaned_test_databases("postgresql:///mlb_test")

    # Both databases should be dropped
    assert result == ["mlb_test_orphan1", "mlb_test_orphan2"]
    # Verify DROP was called twice
    drop_calls = [c for c in mock_cursor.execute.call_args_list if "DROP DATABASE" in str(c)]
    assert len(drop_calls) == 2


@patch("mlb_baseball.reap_test_databases.time.sleep")
@patch("mlb_baseball.reap_test_databases.psycopg.connect")
def test_reap_returns_empty_list_when_no_orphans_in_first_pass(mock_connect, mock_sleep):
    """If no orphaned databases exist in first pass, return empty and don't
    wait."""
    # Setup mock connection and cursor
    mock_conn = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_conn
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    # First pass: no orphans
    mock_cursor.fetchall.return_value = []

    result = reap_orphaned_test_databases("postgresql:///mlb_test")

    # Should return empty list
    assert result == []
    # time.sleep should not be called (optimization: early return)
    mock_sleep.assert_not_called()
