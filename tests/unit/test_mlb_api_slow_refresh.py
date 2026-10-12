"""Hourly roster/transaction/draft refresh: skip when due-time not reached or data unchanged."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pandas as pd

from mlb_baseball import manifest
from mlb_baseball.connectors import mlb_api


def _df(value: str) -> pd.DataFrame:
    return pd.DataFrame({"transaction_id": [1], "description": [value]})


def test_unchanged_fetch_writes_nothing_second_time(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    conn = Mock()
    with patch.object(mlb_api, "load_dataframe", Mock(return_value=1)) as load:
        first = mlb_api._load_slow(conn, "transaction", _df("a"), "raw.t", "_season", "2026", True)
        second = mlb_api._load_slow(conn, "transaction", _df("a"), "raw.t", "_season", "2026", True)
        third = mlb_api._load_slow(conn, "transaction", _df("b"), "raw.t", "_season", "2026", True)
    assert (first, second, third) == (1, 0, 1)
    assert load.call_count == 2


def test_failed_load_is_retried_not_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    boom = Mock(side_effect=RuntimeError("db down"))
    with patch.object(mlb_api, "load_dataframe", boom):
        try:
            mlb_api._load_slow(Mock(), "roster", _df("a"), "raw.t", "_season", "2026", True)
        except RuntimeError:
            pass
    with patch.object(mlb_api, "load_dataframe", Mock(return_value=1)) as load:
        assert mlb_api._load_slow(Mock(), "roster", _df("a"), "raw.t", "_season", "2026", True) == 1
    assert load.call_count == 1


def test_slow_tables_are_due_only_once_an_hour(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    now = datetime.now(UTC)
    assert mlb_api._slow_due("roster", now)
    mlb_api._record_slow_check("roster", "x", now)
    assert not mlb_api._slow_due("roster", now + timedelta(minutes=5))
    assert mlb_api._slow_due("roster", now + timedelta(minutes=61))
