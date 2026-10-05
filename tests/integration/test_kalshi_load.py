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


def _market(
    ticker, event_ticker, status="active", open_time=None, close_time=None, settlement_ts=None
):
    # open_time/close_time are always present keys (possibly None) rather
    # than omitted entirely — real Kalshi market objects always carry both
    # fields (confirmed directly), so a fixture that omits the key outright
    # would create a raw.kalshi_market with no such column at all, which
    # doesn't match production and would break _candle_markets' own
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
        "settlement_ts": settlement_ts,
    }


@pytest.fixture(autouse=True)
def _clean_tables(db_conn):
    yield
    db_conn.rollback()  # a failed assertion can leave the connection mid-transaction
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


def _fake_kalshi(
    monkeypatch, series, events_by_series, markets_by_series, historical_by_series=None
):
    historical_by_series = historical_by_series or {}

    def fake_get(url, params=None, timeout=None):
        if url.endswith("/series"):
            return FakeResponse({"series": series})
        ticker = params["series_ticker"]
        if url.endswith("/events"):
            return FakeResponse({"events": events_by_series.get(ticker, []), "cursor": ""})
        if url.endswith("/historical/markets"):
            return FakeResponse({"markets": historical_by_series.get(ticker, []), "cursor": ""})
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
    # The backfill table only exists after the owner-triggered backfill_history():
    # not having run it is reported as a state, not a missing-table defect.
    assert checks[kalshi.CANDLE_TABLE].ok
    assert "not run" in checks[kalshi.CANDLE_TABLE].detail


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


# --- Candlestick backfill (odds-bulk-history section 4) ------------------
# fetch_market_candles' chunking and _flatten_candlestick's parsing are pure logic and are
# unit-tested in tests/unit/test_kalshi_scope.py; these cover the parts that touch Postgres.


def test_market_absent_from_a_later_pull_is_kept(db_conn, monkeypatch):
    """Catalog history: a market the source stops returning must not be deleted
    (2026-10-03: raw.kalshi_market lost 14,594 rows to whole-table replace)."""
    both = [_market("KXMLBGAME-1-A", "KXMLBGAME-1"), _market("KXMLBGAME-1-B", "KXMLBGAME-1")]
    _fake_kalshi(
        monkeypatch,
        series=[_series("KXMLBGAME")],
        events_by_series={"KXMLBGAME": [_event("KXMLBGAME-1", "KXMLBGAME")]},
        markets_by_series={"KXMLBGAME": both},
    )
    kalshi.update()
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT _loaded_at FROM {kalshi.MARKET_TABLE} WHERE ticker = 'KXMLBGAME-1-B'")
        (first_seen,) = cur.fetchone()
    db_conn.rollback()  # release the read lock; the next run replaces rows on its own connection

    _fake_kalshi(
        monkeypatch,
        series=[_series("KXMLBGAME")],
        events_by_series={"KXMLBGAME": [_event("KXMLBGAME-1", "KXMLBGAME")]},
        markets_by_series={"KXMLBGAME": both[:1]},
    )
    kalshi.update()

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT ticker, _loaded_at FROM {kalshi.MARKET_TABLE} ORDER BY ticker")
        rows = cur.fetchall()
    assert [r[0] for r in rows] == ["KXMLBGAME-1-A", "KXMLBGAME-1-B"]
    assert rows[1][1] == first_seen  # last-seen not advanced for the vanished market
    assert rows[0][1] > first_seen  # still-returned market is refreshed


def test_changed_market_values_replace_the_row(db_conn, monkeypatch):
    def run(last_price):
        market = _market("KXMLBGAME-1-A", "KXMLBGAME-1")
        market["last_price_dollars"] = last_price
        _fake_kalshi(
            monkeypatch,
            series=[_series("KXMLBGAME")],
            events_by_series={"KXMLBGAME": [_event("KXMLBGAME-1", "KXMLBGAME")]},
            markets_by_series={"KXMLBGAME": [market]},
        )
        kalshi.update()

    run("0.52")
    run("0.61")

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT last_price_dollars FROM {kalshi.MARKET_TABLE}")
        assert cur.fetchall() == [("0.61",)]


# --- Snapshot-only capture (odds-history-capture) --------------------------


def _snapshot_get(monkeypatch, markets, calls):
    def fake_get(url, params=None, timeout=None):
        calls.append((url.rsplit("/", 1)[-1], dict(params or {})))
        if url.endswith("/series"):
            return FakeResponse({"series": [_series("KXMLBGAME")]})
        if url.endswith("/markets"):
            return FakeResponse({"markets": markets, "cursor": ""})
        raise AssertionError(f"snapshot must not call {url}")

    monkeypatch.setattr(kalshi.requests, "get", fake_get)


def test_snapshot_keeps_every_capture_with_its_own_time(db_conn, monkeypatch):
    markets = [_market("KXMLBGAME-1-A", "KXMLBGAME-1")]
    _snapshot_get(monkeypatch, markets, [])
    kalshi.snapshot()
    markets[0] = {**markets[0], "last_price_dollars": "0.70"}
    kalshi.snapshot()

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT last_price_dollars FROM {kalshi.SNAPSHOT_TABLE} ORDER BY captured_at")
        assert cur.fetchall() == [("0.52",), ("0.70",)]


def test_snapshot_reads_only_open_markets_and_leaves_the_catalog_alone(db_conn, monkeypatch):
    calls = []
    _snapshot_get(monkeypatch, [_market("KXMLBGAME-1-A", "KXMLBGAME-1")], calls)

    counts = kalshi.snapshot()

    assert counts[kalshi.SNAPSHOT_TABLE] == 1
    assert {name for name, _ in calls} == {"series", "markets"}  # no /events
    assert all(p.get("status") == "open" for name, p in calls if name == "markets")
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (kalshi.MARKET_TABLE,))
        assert cur.fetchone() == (None,)  # catalog tables untouched


def test_snapshot_with_no_open_markets_succeeds_and_creates_the_table(db_conn, monkeypatch):
    _snapshot_get(monkeypatch, [], [])

    counts = kalshi.snapshot()

    assert counts[kalshi.SNAPSHOT_TABLE] == 0
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {kalshi.SNAPSHOT_TABLE}")
        assert cur.fetchone() == (0,)


def test_catalog_includes_markets_only_the_historical_listing_has(db_conn, monkeypatch):
    _fake_kalshi(
        monkeypatch,
        series=[_series("KXMLBGAME")],
        events_by_series={},
        markets_by_series={"KXMLBGAME": [_market("KXMLBGAME-NEW-A", "KXMLBGAME-NEW")]},
        historical_by_series={
            "KXMLBGAME": [
                _market("KXMLBGAME-OLD-A", "KXMLBGAME-OLD", status="finalized"),
                _market("KXMLBGAME-NEW-A", "KXMLBGAME-NEW", status="finalized"),  # also live
            ]
        },
    )

    kalshi.bootstrap()

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT ticker, status FROM {kalshi.MARKET_TABLE} ORDER BY ticker")
        # live wins on a ticker present in both
        assert cur.fetchall() == [("KXMLBGAME-NEW-A", "active"), ("KXMLBGAME-OLD-A", "finalized")]


# -- fast candle backfill ----------------------------------------------------

_CUTOFF = "2026-08-06T00:00:00Z"


def _candle(ts, *, trade=False):
    return {
        "end_period_ts": ts,
        "open_interest_fp": "1.00",
        "price": {"close_dollars": "0.5"} if trade else {},
        "volume_fp": "2.00",
        "yes_bid": {"close_dollars": "0.48"} if trade else {},
        "yes_ask": {"close_dollars": "0.52"} if trade else {},
    }


class FakeCandles:
    """Mimics the endpoints that matter here: `/historical/markets/{t}/candlesticks` only knows
    markets settled before the cutoff, the live path only knows later ones, and a window of more
    than 5,000 candles is a 400."""

    def __init__(self, fail_tickers=()):
        self.calls = []
        self.fail_tickers = set(fail_tickers)

    def __call__(self, url, params):
        import requests

        self.calls.append((url, dict(params)))
        ticker = url.split("/markets/")[1].split("/")[0]
        if ticker in self.fail_tickers:
            raise requests.exceptions.ConnectionError("source went away")
        assert (params["end_ts"] - params["start_ts"]) / 60 <= 5000
        historical = "/historical/" in url
        settled_before_cutoff = ticker.startswith("OLD")
        if historical != settled_before_cutoff:
            reply = requests.Response()
            reply.status_code = 404
            raise requests.exceptions.HTTPError(response=reply)
        return {"candlesticks": [_candle(params["start_ts"] + 60, trade=True)], "ticker": ticker}


def _seed_markets(monkeypatch, markets):
    _fake_kalshi(
        monkeypatch,
        series=[_series("KXMLBGAME")],
        events_by_series={},
        markets_by_series={"KXMLBGAME": markets},
    )
    kalshi.bootstrap()


def _run_candles(monkeypatch, fake):
    monkeypatch.setattr(kalshi, "_candle_get", fake)
    monkeypatch.setattr(kalshi, "fetch_cutoff", lambda: {"market_settled_ts": _CUTOFF})
    monkeypatch.setattr(kalshi, "BACKFILL_RETRY_BACKOFF_SECONDS", 0)
    return kalshi.backfill_history()


@pytest.fixture
def _candle_ledger_clean(db_conn):
    yield
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute(
            "DELETE FROM meta.ingestion_item WHERE source = %s AND dataset = %s",
            (kalshi.SOURCE, kalshi.CANDLE_DATASET),
        )
        cur.execute("DELETE FROM meta.ingestion_run WHERE source = %s", (kalshi.BACKFILL_SOURCE,))
    db_conn.commit()


def _times(close="2026-07-01T02:00:00Z", settled="2026-07-01T02:05:00Z"):
    return {"open_time": "2026-07-01T00:00:00Z", "close_time": close, "settlement_ts": settled}


def test_backfill_reads_markets_settled_before_the_cutoff_from_the_historical_endpoint(
    db_conn, monkeypatch, _candle_ledger_clean
):
    _seed_markets(
        monkeypatch,
        [
            _market("OLD-1-A", "OLD-1", **_times()),
            _market("NEW-1-A", "NEW-1", **_times(settled="2026-09-01T02:05:00Z")),
        ],
    )
    fake = FakeCandles()

    counts = _run_candles(monkeypatch, fake)

    assert counts[kalshi.CANDLE_TABLE] == 2
    urls = {u for u, _ in fake.calls}
    assert any("/historical/markets/OLD-1-A/candlesticks" in u for u in urls)
    assert any("/series/NEW/markets/NEW-1-A/candlesticks" in u for u in urls)


def test_backfill_falls_back_to_the_other_endpoint_on_a_404(
    db_conn, monkeypatch, _candle_ledger_clean
):
    # settled just after the cutoff by our reading, but the market is already archived
    _seed_markets(
        monkeypatch, [_market("OLD-1-A", "OLD-1", **_times(settled="2026-08-07T00:00:00Z"))]
    )
    fake = FakeCandles()
    counts = _run_candles(monkeypatch, fake)
    assert counts[kalshi.CANDLE_TABLE] == 1
    assert [("/historical/" in u) for u, _ in fake.calls] == [False, True]


def test_backfill_rerun_skips_settled_markets_and_does_not_duplicate(
    db_conn, monkeypatch, _candle_ledger_clean
):
    _seed_markets(monkeypatch, [_market("OLD-1-A", "OLD-1", **_times())])
    fake = FakeCandles()
    _run_candles(monkeypatch, fake)
    first_calls = len(fake.calls)
    _run_candles(monkeypatch, fake)

    assert len(fake.calls) == first_calls  # nothing fetched again
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {kalshi.CANDLE_TABLE}")
        assert cur.fetchone() == (1,)


def test_backfill_cuts_a_long_market_into_windows_under_the_candle_limit(
    db_conn, monkeypatch, _candle_ledger_clean
):
    _seed_markets(
        monkeypatch,
        [_market("OLD-1-A", "OLD-1", **_times(close="2026-07-08T00:00:00Z"))],  # 7 days
    )
    fake = FakeCandles()
    _run_candles(monkeypatch, fake)
    assert len(fake.calls) == 3  # 10,080 minutes in windows of 4,000


def test_backfill_remembers_a_market_with_no_candles(db_conn, monkeypatch, _candle_ledger_clean):
    _seed_markets(monkeypatch, [_market("OLD-1-A", "OLD-1", **_times())])

    class Empty(FakeCandles):
        def __call__(self, url, params):
            super().__call__(url, params)
            return {"candlesticks": []}

    fake = Empty()
    counts = _run_candles(monkeypatch, fake)
    assert counts[kalshi.CANDLE_TABLE] == 0
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT status, rows FROM meta.ingestion_item WHERE source = %s AND dataset = %s",
            (kalshi.SOURCE, kalshi.CANDLE_DATASET),
        )
        assert cur.fetchall() == [("unavailable", 0)]


def test_backfill_records_a_failure_keeps_going_and_a_rerun_retries_only_it(
    db_conn, monkeypatch, _candle_ledger_clean
):
    _seed_markets(
        monkeypatch,
        [_market("OLD-1-A", "OLD-1", **_times()), _market("OLD-2-A", "OLD-2", **_times())],
    )
    with pytest.raises(RuntimeError, match="failed"):
        _run_candles(monkeypatch, FakeCandles(fail_tickers={"OLD-2-A"}))
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT item_key, status FROM meta.ingestion_item "
            "WHERE source = %s AND dataset = %s ORDER BY 1",
            (kalshi.SOURCE, kalshi.CANDLE_DATASET),
        )
        assert cur.fetchall() == [("OLD-1-A", "loaded"), ("OLD-2-A", "failed")]

    retry = FakeCandles()
    _run_candles(monkeypatch, retry)
    assert {u.split("/markets/")[1].split("/")[0] for u, _ in retry.calls} == {"OLD-2-A"}
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT ticker, count(*) FROM {kalshi.CANDLE_TABLE} GROUP BY 1 ORDER BY 1")
        assert cur.fetchall() == [("OLD-1-A", 1), ("OLD-2-A", 1)]


def test_backfill_skips_markets_without_open_or_close_time(
    db_conn, monkeypatch, _candle_ledger_clean
):
    _seed_markets(monkeypatch, [_market("OLD-1-A", "OLD-1")])  # no times
    fake = FakeCandles()
    counts = _run_candles(monkeypatch, fake)
    assert counts[kalshi.CANDLE_TABLE] == 0
    assert fake.calls == []


def test_a_candle_with_no_trade_stores_no_price_never_zero(
    db_conn, monkeypatch, _candle_ledger_clean
):
    _seed_markets(monkeypatch, [_market("OLD-1-A", "OLD-1", **_times())])

    class NoTrade(FakeCandles):
        def __call__(self, url, params):
            super().__call__(url, params)
            return {"candlesticks": [_candle(params["start_ts"] + 60, trade=False)]}

    _run_candles(monkeypatch, NoTrade())
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'raw' AND table_name = 'kalshi_candle' "
            "AND (column_name LIKE 'price%' OR column_name LIKE 'yes_%')"
        )
        price_columns = [name for (name,) in cur.fetchall()]
        # all columns exist up front, but a no-trade candle leaves every price NULL: never 0
        cur.execute(
            "SELECT "
            + ", ".join(f'"{c}" IS NULL' for c in price_columns)
            + " FROM raw.kalshi_candle"
        )
        assert all(cur.fetchone())


def test_backfill_holds_neither_the_workflow_lock_nor_the_update_source_lock(
    db_conn, monkeypatch, _candle_ledger_clean
):
    from mlb_baseball.ingest import track_run

    _seed_markets(monkeypatch, [_market("OLD-1-A", "OLD-1", **_times())])
    seen = {}

    class Probe(FakeCandles):
        def __call__(self, url, params):
            with track_run(db_conn, kalshi.SOURCE, "update", workflow="exclusive") as result:
                result["rows"] = 0
                seen["ok"] = True
            return super().__call__(url, params)

    _run_candles(monkeypatch, Probe())
    assert seen == {"ok": True}


def test_backfill_reports_progress_to_the_monitor(db_conn, monkeypatch, _candle_ledger_clean):
    _seed_markets(monkeypatch, [_market("OLD-1-A", "OLD-1", **_times())])
    _run_candles(monkeypatch, FakeCandles())
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT items_planned, items_done FROM meta.ingestion_run "
            "WHERE source = %s ORDER BY id DESC LIMIT 1",
            (kalshi.BACKFILL_SOURCE,),
        )
        assert cur.fetchone() == (1, 1)
        cur.execute("DELETE FROM meta.op_span WHERE op = 'kalshi.candles'")
    db_conn.commit()


def test_candle_backfill_takes_short_lived_markets_before_season_long_ones(
    db_conn, monkeypatch, _candle_ledger_clean
):
    day = {"open_time": "2026-07-01T00:00:00Z", "settlement_ts": "2026-07-01T02:05:00Z"}
    _seed_markets(
        monkeypatch,
        [
            _market("OLD-LONG-A", "OLD-LONG", close_time="2026-07-31T00:00:00Z", **day),  # 30 days
            _market("OLD-SHORT-A", "OLD-SHORT", close_time="2026-07-01T05:00:00Z", **day),
            _market("OLD-SHORT-B", "OLD-SHORT2", close_time="2026-07-02T05:00:00Z", **day),
        ],
    )
    markets = kalshi._candle_markets(db_conn)
    assert [m["ticker"] for m in markets] == ["OLD-SHORT-A", "OLD-SHORT-B", "OLD-LONG-A"]


def test_many_markets_written_concurrently_do_not_deadlock(
    db_conn, monkeypatch, _candle_ledger_clean
):
    """121 of the first 5,000 production markets failed with `deadlock detected` when eight
    workers wrote at once (each write ran CREATE INDEX IF NOT EXISTS, a table-level lock)."""
    _seed_markets(monkeypatch, [_market(f"OLD-{i}-A", f"OLD-{i}", **_times()) for i in range(60)])
    counts = _run_candles(monkeypatch, FakeCandles())
    assert counts[kalshi.CANDLE_TABLE] == 60
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM meta.ingestion_item "
            "WHERE source = %s AND dataset = %s AND status = 'failed'",
            (kalshi.SOURCE, kalshi.CANDLE_DATASET),
        )
        assert cur.fetchone() == (0,)
