"""Real DB, real DataFrame/COPY loading — only requests.get is mocked."""

import pytest

from mlb_baseball.connectors import kalshi

ALL_TABLES = [kalshi.SERIES_TABLE, kalshi.EVENT_TABLE, kalshi.MARKET_TABLE]


def _series(ticker):
    return {"ticker": ticker, "title": f"Series {ticker}", "category": "Sports"}


def _event(event_ticker, series_ticker):
    return {"event_ticker": event_ticker, "series_ticker": series_ticker, "title": "Some Event"}


def _market(ticker, event_ticker):
    return {
        "ticker": ticker,
        "event_ticker": event_ticker,
        "status": "active",
        "yes_bid_dollars": "0.50",
        "yes_ask_dollars": "0.55",
    }


@pytest.fixture(autouse=True)
def _clean_tables(db_conn):
    yield
    with db_conn.cursor() as cur:
        for table in ALL_TABLES:
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

    assert counts == dict.fromkeys(ALL_TABLES, 0)


def test_health_check_reports_last_run(db_conn, monkeypatch):
    _fake_kalshi(
        monkeypatch,
        series=[_series("KXMLBGAME")],
        events_by_series={"KXMLBGAME": [_event("KXMLBGAME-1", "KXMLBGAME")]},
        markets_by_series={"KXMLBGAME": [_market("KXMLBGAME-1-A", "KXMLBGAME-1")]},
    )

    kalshi.bootstrap()

    checks = kalshi.health_check()

    assert any(c.name == f"{kalshi.SOURCE} last run" for c in checks)
    assert all(c.ok for c in checks)


def test_fetch_events_uses_a_smaller_page_size_than_markets():
    # Regression: /events rejects limit values /markets happily accepts
    # (confirmed directly against the real API: limit=1000 200s on
    # /markets but 400s on /events; 200 is the largest confirmed-safe
    # value for /events).
    assert kalshi.EVENTS_PAGE_SIZE < kalshi.MARKETS_PAGE_SIZE
