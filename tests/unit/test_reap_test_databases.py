from unittest.mock import MagicMock

from mlb_baseball.reap_test_databases import find_orphaned_test_databases


def test_finds_databases_matching_pattern_with_no_active_connections():
    cur = MagicMock()
    cur.execute.return_value = None
    cur.fetchall.return_value = [("mlb_test_abc123",), ("mlb_test_def456",)]

    result = find_orphaned_test_databases(cur)

    assert result == ["mlb_test_abc123", "mlb_test_def456"]
    (query, params), _ = cur.execute.call_args
    assert "mlb\\_test\\_%" in query or "mlb\\_test\\_%" in params
