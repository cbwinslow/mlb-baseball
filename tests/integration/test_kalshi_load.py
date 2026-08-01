"""Real DB, real DataFrame/COPY loading — only requests.get is mocked."""

import pytest

from mlb_baseball.connectors import kalshi

ALL_TABLES = [kalshi.SERIES_TABLE, kalshi.EVENT_TABLE, kalshi.MARKET_TABLE]
# Tables this test file's fixtures might create, beyond ALL_TABLES above —
# dropped after every test regardless of which ones a given test actually
# touched (raw.kalshi_candle only exists once backfill_history() runs).
_CLEANUP_TABLES = [*ALL_TABLES, kalshi.SNAPSHOT_TABLE, kalshi.CANDLE_TABLE]


def _series(ticker):
    return {"ticker": ticker, "title": f"Series {ticker}", "category": "Sports"}


def _event(event_ticker, series_ticker):
    return {"event_ticker": event_ticker, "series_ticker": series_ticker, "title": "Some Event"}


def _market(ticker, event_ticker, status="active", open_time=None, close_time=None):
    # open_time/close_time are always present keys (possibly None) rather
    # than omitted entirely — real Kalshi market objects always carry both
    # fields (confirmed directly), so a fixture that omits the key outright
    # would create a raw.kalshi_market with no such column at all, which
    # doesn't match production and would break _kxmlbgame_markets' own
    # SELECT.
    return {
        "ticker": ticker,
        "event_ticker": event_ticker,
        "status": status,
        "yes_bid_dollars": "0.50",
        "yes_ask_dollars": "0.55",
        "last_price_dollars": "0.52",
        "volume_fp": "10.00",
        "open_interest_fp": "5.00",
        "open_time": open_time,
        "close_time": close_time,
    }


@pytest.fixture(autouse=True)
def _clean_tables(db_conn):
    yield
    with db_conn.cursor() as cur:
        for table in _CLEANUP_TABLES:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute("DELETE FROM meta.ingestion_run WHERE source = %s", (kalshi.SOURCE,))
    db_conn.commit()


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _fake_kalshi(monkeypatch, series, events_by_series, markets_by_series):
    def fake_get(url, params=None, timeout=None):
        if url.endswith("/series"):
            return FakeResponse({"series": series})
        ticker = params["series_ticker"]
        if url.endswith("/events"):
            return FakeResponse({"events": events_by_series.get(ticker, []), "cursor": ""})
        if url.endswith("/markets"):
            return FakeResponse({"markets": markets_by_series.get(ticker, []), "cursor": ""})
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(kalshi.requests, "get", fake_get)


def test_run_loads_series_event_and_market_tables(db_conn, monkeypatch):
    _fake_kalshi(
        monkeypatch,
        series=[_series("KXMLBGAME")],
        events_by_series={"KXMLBGAME": [_event("KXMLBGAME-1", "KXMLBGAME")]},
        markets_by_series={
            "KXMLBGAME": [
                _market("KXMLBGAME-1-A", "KXMLBGAME-1"),
                _market("KXMLBGAME-1-B", "KXMLBGAME-1"),
            ]
        },
    )

    counts = kalshi.bootstrap()

    assert counts[kalshi.SERIES_TABLE] == 1
    assert counts[kalshi.EVENT_TABLE] == 1
    assert counts[kalshi.MARKET_TABLE] == 2
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {kalshi.MARKET_TABLE}")
        assert cur.fetchone() == (2,)


def test_rerunning_replaces_instead_of_duplicating(db_conn, monkeypatch):
    _fake_kalshi(
        monkeypatch,
        series=[_series("KXMLBGAME")],
        events_by_series={"KXMLBGAME": [_event("KXMLBGAME-1", "KXMLBGAME")]},
        markets_by_series={"KXMLBGAME": [_market("KXMLBGAME-1-A", "KXMLBGAME-1")]},
    )

    kalshi.bootstrap()
    kalshi.update()

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {kalshi.MARKET_TABLE}")
        assert cur.fetchone() == (1,)


def test_run_skips_a_failing_series_and_continues(db_conn, monkeypatch):
    def fake_get(url, params=None, timeout=None):
        if url.endswith("/series"):
            return FakeResponse({"series": [_series("KXMLBGAME"), _series("KXMLBWS")]})
        ticker = params["series_ticker"]
        if ticker == "KXMLBGAME":
            raise Exception("simulated Kalshi outage")
        if url.endswith("/events"):
            return FakeResponse({"events": [_event("KXMLBWS-1", "KXMLBWS")], "cursor": ""})
        if url.endswith("/markets"):
            return FakeResponse({"markets": [_market("KXMLBWS-1-A", "KXMLBWS-1")], "cursor": ""})
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(kalshi.requests, "get", fake_get)

    counts = kalshi.bootstrap()

    assert counts[kalshi.SERIES_TABLE] == 2
    assert counts[kalshi.MARKET_TABLE] == 1  # only KXMLBWS's market landed
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {kalshi.EVENT_TABLE}")
        assert cur.fetchone() == (1,)


def test_run_handles_no_series_without_erroring(db_conn, monkeypatch):
    _fake_kalshi(monkeypatch, series=[], events_by_series={}, markets_by_series={})

    counts = kalshi.bootstrap()

    assert counts == {**dict.fromkeys(ALL_TABLES, 0), kalshi.SNAPSHOT_TABLE: 0}


def test_health_check_reports_last_run(db_conn, monkeypatch):
    _fake_kalshi(
        monkeypatch,
        series=[_series("KXMLBGAME")],
        events_by_series={"KXMLBGAME": [_event("KXMLBGAME-1", "KXMLBGAME")]},
        markets_by_series={"KXMLBGAME": [_market("KXMLBGAME-1-A", "KXMLBGAME-1")]},
    )

    kalshi.bootstrap()

    checks = {c.name: c for c in kalshi.health_check()}

    assert checks[f"{kalshi.SOURCE} last run"].ok
    assert checks[kalshi.SERIES_TABLE].ok
    assert checks[kalshi.EVENT_TABLE].ok
    assert checks[kalshi.MARKET_TABLE].ok
    # raw.kalshi_snapshot is guaranteed to exist after any bootstrap()/
    # update() run (same fix as raw.mlb_live_game — see _run()'s own
    # comment).
    assert checks[kalshi.SNAPSHOT_TABLE].ok
    # raw.kalshi_candle only exists once backfill_history() has actually
    # been run at least once (an owner-triggered one-off, not part of
    # bootstrap()/update()) — correctly reported unhealthy here, not a
    # false negative.
    assert not checks[kalshi.CANDLE_TABLE].ok


def test_fetch_events_uses_a_smaller_page_size_than_markets():
    # Regression: /events rejects limit values /markets happily accepts
    # (confirmed directly against the real API: limit=1000 200s on
    # /markets but 400s on /events; 200 is the largest confirmed-safe
    # value for /events).
    assert kalshi.EVENTS_PAGE_SIZE < kalshi.MARKETS_PAGE_SIZE


# --- Forward snapshots (ADR-047) ---------------------------------------


def test_run_appends_snapshot_only_for_active_markets(db_conn, monkeypatch):
    _fake_kalshi(
        monkeypatch,
        series=[_series("KXMLBGAME")],
        events_by_series={"KXMLBGAME": [_event("KXMLBGAME-1", "KXMLBGAME")]},
        markets_by_series={
            "KXMLBGAME": [
                _market("KXMLBGAME-1-A", "KXMLBGAME-1", status="active"),
                _market("KXMLBGAME-1-B", "KXMLBGAME-1", status="finalized"),
            ]
        },
    )

    counts = kalshi.bootstrap()

    assert counts[kalshi.SNAPSHOT_TABLE] == 1  # only the active market
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {kalshi.SNAPSHOT_TABLE}")
        assert cur.fetchone() == (1,)


def test_run_snapshot_accumulates_across_runs(db_conn, monkeypatch):
    _fake_kalshi(
        monkeypatch,
        series=[_series("KXMLBGAME")],
        events_by_series={"KXMLBGAME": [_event("KXMLBGAME-1", "KXMLBGAME")]},
        markets_by_series={"KXMLBGAME": [_market("KXMLBGAME-1-A", "KXMLBGAME-1", status="active")]},
    )

    kalshi.bootstrap()
    kalshi.update()

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {kalshi.SNAPSHOT_TABLE}")
        assert cur.fetchone() == (2,)  # 1 market x 2 runs, append-only


def test_snapshot_table_exists_even_with_no_active_markets(db_conn, monkeypatch):
    _fake_kalshi(monkeypatch, series=[], events_by_series={}, markets_by_series={})

    kalshi.bootstrap()

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {kalshi.SNAPSHOT_TABLE}")
        assert cur.fetchone() == (0,)


# --- Candlestick backfill (ADR-047) --------------------------------------
# fetch_candlesticks' chunking and _flatten_candlestick's parsing are pure
# logic (fetch_candlesticks mocks HTTP, no DB) and are unit-tested in
# tests/unit/test_kalshi_scope.py instead — these cover the parts that
# actually touch Postgres.


def test_backfill_history_loads_candles_scoped_by_ticker(db_conn, monkeypatch):
    _fake_kalshi(
        monkeypatch,
        series=[_series("KXMLBGAME")],
        events_by_series={"KXMLBGAME": [_event("KXMLBGAME-1", "KXMLBGAME")]},
        markets_by_series={
            "KXMLBGAME": [
                _market(
                    "KXMLBGAME-1-A",
                    "KXMLBGAME-1",
                    open_time="2026-07-01T00:00:00Z",
                    close_time="2026-07-01T02:00:00Z",
                )
            ]
        },
    )
    kalshi.bootstrap()

    def fake_candle_get(url, params=None, timeout=None):
        return FakeResponse(
            {
                "candlesticks": [
                    {
                        "end_period_ts": params["start_ts"] + 60,
                        "open_interest_fp": "1.00",
                        "price": {"close_dollars": "0.5"},
                        "volume_fp": "2.00",
                        "yes_bid": {"close_dollars": "0.48"},
                        "yes_ask": {"close_dollars": "0.52"},
                    }
                ]
            }
        )

    monkeypatch.setattr(kalshi.requests, "get", fake_candle_get)
    counts = kalshi.backfill_history()

    assert counts[kalshi.CANDLE_TABLE] == 1
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {kalshi.CANDLE_TABLE}")
        assert cur.fetchone() == (1,)


def test_backfill_history_rerunning_replaces_instead_of_duplicating(db_conn, monkeypatch):
    _fake_kalshi(
        monkeypatch,
        series=[_series("KXMLBGAME")],
        events_by_series={"KXMLBGAME": [_event("KXMLBGAME-1", "KXMLBGAME")]},
        markets_by_series={
            "KXMLBGAME": [
                _market(
                    "KXMLBGAME-1-A",
                    "KXMLBGAME-1",
                    open_time="2026-07-01T00:00:00Z",
                    close_time="2026-07-01T02:00:00Z",
                )
            ]
        },
    )
    kalshi.bootstrap()

    def fake_candle_get(url, params=None, timeout=None):
        return FakeResponse(
            {
                "candlesticks": [
                    {
                        "end_period_ts": params["start_ts"] + 60,
                        "open_interest_fp": "1.00",
                        "price": {},
                        "volume_fp": "2.00",
                        "yes_bid": {},
                        "yes_ask": {},
                    }
                ]
            }
        )

    monkeypatch.setattr(kalshi.requests, "get", fake_candle_get)
    kalshi.backfill_history()
    kalshi.backfill_history()

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {kalshi.CANDLE_TABLE}")
        assert cur.fetchone() == (1,)  # not doubled


def test_backfill_history_skips_markets_without_open_or_close_time(db_conn, monkeypatch):
    _fake_kalshi(
        monkeypatch,
        series=[_series("KXMLBGAME")],
        events_by_series={"KXMLBGAME": [_event("KXMLBGAME-1", "KXMLBGAME")]},
        markets_by_series={"KXMLBGAME": [_market("KXMLBGAME-1-A", "KXMLBGAME-1")]},  # no times
    )
    kalshi.bootstrap()

    def fail_get(url, params=None, timeout=None):
        raise AssertionError("candlesticks should never be requested for this market")

    monkeypatch.setattr(kalshi.requests, "get", fail_get)
    counts = kalshi.backfill_history()

    assert counts[kalshi.CANDLE_TABLE] == 0
