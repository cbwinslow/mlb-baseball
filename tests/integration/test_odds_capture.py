"""Real DB: the odds-capture gate and runner. Connector snapshots are stubbed
(their own behaviour is covered in test_kalshi_load / test_polymarket_load)."""

from datetime import date, timedelta

import pytest

from mlb_baseball import odds_capture

TODAY = date(2026, 7, 4)


@pytest.fixture(autouse=True)
def _clean_schedule(db_conn):
    yield
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
    db_conn.commit()


def _schedule(db_conn, *game_dates):
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
        cur.execute("CREATE TABLE raw.mlb_schedule (game_id text, game_date text)")
        for i, d in enumerate(game_dates):
            cur.execute("INSERT INTO raw.mlb_schedule VALUES (%s, %s)", (str(i), d.isoformat()))
    db_conn.commit()


def test_games_scheduled_today(db_conn):
    _schedule(db_conn, TODAY)
    assert odds_capture.games_scheduled(db_conn, today=TODAY) is True


def test_games_scheduled_tomorrow_or_yesterday_count_for_time_zones(db_conn):
    # A US evening game is already "tomorrow" in UTC; a late one ends "yesterday".
    _schedule(db_conn, TODAY + timedelta(days=1))
    assert odds_capture.games_scheduled(db_conn, today=TODAY) is True
    _schedule(db_conn, TODAY - timedelta(days=1))
    assert odds_capture.games_scheduled(db_conn, today=TODAY) is True


def test_no_games_in_the_window(db_conn):
    _schedule(db_conn, TODAY + timedelta(days=30), TODAY - timedelta(days=30))
    assert odds_capture.games_scheduled(db_conn, today=TODAY) is False


def test_unknown_schedule_fails_open(db_conn):
    # No schedule table at all: we cannot know, so capture rather than lose data.
    assert odds_capture.games_scheduled(db_conn, today=TODAY) is True


def test_run_skips_both_snapshots_when_no_games(monkeypatch):
    calls = []
    monkeypatch.setattr(odds_capture, "_games_scheduled_now", lambda: False)
    monkeypatch.setattr(odds_capture.kalshi, "snapshot", lambda: calls.append("k") or {})
    monkeypatch.setattr(odds_capture.polymarket, "snapshot", lambda: calls.append("p") or {})

    assert odds_capture.run() == {}
    assert calls == []


def test_run_continues_to_the_other_source_when_one_fails_then_raises(monkeypatch):
    calls = []

    def boom():
        raise RuntimeError("kalshi down")

    monkeypatch.setattr(odds_capture, "_games_scheduled_now", lambda: True)
    monkeypatch.setattr(odds_capture.kalshi, "snapshot", boom)
    monkeypatch.setattr(
        odds_capture.polymarket, "snapshot", lambda: calls.append("p") or {"raw.p": 2}
    )

    with pytest.raises(RuntimeError, match="kalshi"):
        odds_capture.run()
    assert calls == ["p"]  # polymarket still captured


def test_run_returns_both_counts(monkeypatch):
    monkeypatch.setattr(odds_capture, "_games_scheduled_now", lambda: True)
    monkeypatch.setattr(odds_capture.kalshi, "snapshot", lambda: {"raw.k": 1})
    monkeypatch.setattr(odds_capture.polymarket, "snapshot", lambda: {"raw.p": 2})

    assert odds_capture.run() == {"raw.k": 1, "raw.p": 2}
