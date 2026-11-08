"""Hourly roster/transaction/draft refresh: skip when due-time not reached or data unchanged."""

import json
from datetime import UTC, date, datetime, timedelta
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


def test_tick_between_hourly_checks_fetches_none_of_the_hourly_tables(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    now = datetime.now(UTC)
    for key in ("schedule", "standing", "roster", "transaction", "draft"):
        mlb_api._record_slow_check(key, "x", now)
    fetch = Mock(side_effect=AssertionError("hourly table fetched between checks"))
    for name in ("_schedule_df", "_standings_df", "_roster_df", "_transactions_df", "_draft_df"):
        monkeypatch.setattr(mlb_api, name, fetch)
    counts = mlb_api._load_hourly_tables(Mock(), 2026)
    assert set(counts.values()) == {0}
    assert fetch.call_count == 0


def test_hourly_tables_all_load_when_due_and_not_again_when_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    frame = pd.DataFrame({"k": [1]})
    for name in ("_schedule_df", "_standings_df", "_roster_df", "_transactions_df", "_draft_df"):
        monkeypatch.setattr(mlb_api, name, Mock(return_value=frame))
    monkeypatch.setattr(mlb_api, "_load_next_schedule", Mock(return_value=0))
    with patch.object(mlb_api, "load_dataframe", Mock(return_value=1)) as load:
        first = mlb_api._load_hourly_tables(Mock(), 2026)
        # Pretend an hour has passed: the data is identical, so nothing is written.
        for key in ("schedule", "standing", "roster", "transaction", "draft"):
            state = mlb_api._slow_state()
            state[key]["checked_at"] = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
            mlb_api._slow_state_path().write_text(json.dumps(state))
        second = mlb_api._load_hourly_tables(Mock(), 2026)
    assert all(v == 1 for v in first.values()) and len(first) == 5
    assert all(v == 0 for v in second.values())
    assert load.call_count == 5


def test_schedule_days_replaces_only_the_returned_dates(monkeypatch):
    games = [
        {"game_id": 1, "game_date": "2026-10-12", "status": "Final"},
        {"game_id": 2, "game_date": "2026-10-13", "status": "In Progress"},
    ]
    replace = Mock(return_value=2)
    monkeypatch.setattr(mlb_api, "_timed_schedule", Mock(return_value=games))
    monkeypatch.setattr(mlb_api, "replace_dataframe_scopes", replace)
    days = [date(2026, 10, 12), date(2026, 10, 13)]
    assert mlb_api._load_schedule_days(Mock(), days) == 2
    kwargs = replace.call_args.kwargs
    assert kwargs["scope_column"] == "game_date"
    assert kwargs["scope_values"] == ["2026-10-12", "2026-10-13"]
    assert (replace.call_args.args[2]["_season"] == "2026").all()


def test_schedule_days_with_no_games_leaves_existing_rows_alone(monkeypatch):
    replace = Mock()
    monkeypatch.setattr(mlb_api, "_timed_schedule", Mock(return_value=[]))
    monkeypatch.setattr(mlb_api, "replace_dataframe_scopes", replace)
    assert mlb_api._load_schedule_days(Mock(), [date(2026, 12, 25)]) == 0
    assert not replace.called
