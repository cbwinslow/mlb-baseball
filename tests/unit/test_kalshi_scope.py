from unittest.mock import patch

from mlb_baseball.connectors import kalshi


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_excluded_series_tickers_are_all_non_mlb_baseball_leagues():
    # Regression: EXCLUDED_SERIES_TICKERS exists specifically to keep
    # non-MLB baseball (KBO, NPB, WBC, college, MiLB, etc.) out of a
    # "Baseball"-tagged Kalshi series pull — every ticker in it must start
    # with one of these non-MLB prefixes/exact matches, not accidentally
    # exclude a real MLB series.
    non_mlb_markers = (
        "KXKBO",
        "KXLMBGAME",
        "KXMILBGAME",
        "KXNCAA",
        "KXNPB",
        "KXWBC",
        "KXMLBWORLD",
        "KXCONGRESSBASEBALL",
        "KXTEAMSINNCAABBWS",
        "KXNLMOTY",
    )
    for ticker in kalshi.EXCLUDED_SERIES_TICKERS:
        assert ticker.startswith(non_mlb_markers) or ticker in non_mlb_markers, ticker


def test_fetch_series_filters_out_excluded_tickers(monkeypatch):
    def fake_get(url, params):
        return {
            "series": [
                {"ticker": "KXMLBGAME", "title": "Professional Baseball Game"},
                {"ticker": "KXNCAABBGAME", "title": "College Baseball Game"},
                {"ticker": "KXWBCGAME", "title": "World Baseball Classic Game"},
            ]
        }

    monkeypatch.setattr(kalshi, "_get", fake_get)

    series = kalshi.fetch_series()

    assert [s["ticker"] for s in series] == ["KXMLBGAME"]


def test_snapshot_rows_skips_non_active_markets_and_stamps_captured_at():
    markets = [
        {"ticker": "A", "status": "active", "yes_bid_dollars": "0.40"},
        {"ticker": "B", "status": "finalized", "yes_bid_dollars": "0.90"},
    ]

    rows = kalshi._snapshot_rows(markets, "2026-08-01T00:00:00+00:00")

    assert len(rows) == 1
    assert rows[0]["ticker"] == "A"
    assert rows[0]["captured_at"] == "2026-08-01T00:00:00+00:00"


def test_fetch_market_candles_chunks_the_time_range():
    # Regression: a too-wide single request 400s with "max candlesticks: 5000" (confirmed
    # directly against the real API) -- any [start_ts, end_ts] wider than CANDLE_CHUNK_MINUTES
    # must be split into several requests.
    calls = []

    def fake_get(url, params):
        calls.append((url, dict(params)))
        return {"candlesticks": [{"end_period_ts": params["start_ts"] + 60}]}

    chunk_seconds = kalshi.CANDLE_CHUNK_MINUTES * 60
    end_ts = chunk_seconds * 2 + 100  # spans 3 chunks
    with patch.object(kalshi, "_candle_get", side_effect=fake_get):
        candles = kalshi.fetch_market_candles("KXMLBGAME-X-A", 0, end_ts, historical=True)

    assert [p["start_ts"] for _, p in calls] == [0, chunk_seconds, chunk_seconds * 2]
    assert calls[-1][1]["end_ts"] == end_ts
    assert all("/historical/markets/KXMLBGAME-X-A/candlesticks" in u for u, _ in calls)
    assert len(candles) == 3


def test_fetch_market_candles_uses_the_live_series_path_for_a_recent_market():
    urls = []

    def fake_get(url, params):
        urls.append(url)
        return {"candlesticks": []}

    with patch.object(kalshi, "_candle_get", side_effect=fake_get):
        kalshi.fetch_market_candles("KXMLBGAME-X-A", 0, 60, historical=False)

    assert urls == [f"{kalshi.BASE_URL}/series/KXMLBGAME/markets/KXMLBGAME-X-A/candlesticks"]


def test_fetch_market_candles_slows_the_shared_limiter_on_429_and_retries():
    import requests

    from mlb_baseball.net import RateLimiter

    limiter = RateLimiter(40.0)
    attempts = {"n": 0}

    def fake_get(url, params):
        attempts["n"] += 1
        if attempts["n"] == 1:
            reply = requests.Response()
            reply.status_code = 429
            reply.headers["Retry-After"] = "0"
            raise requests.exceptions.HTTPError(response=reply)
        return {"candlesticks": []}

    with patch.object(kalshi, "_candle_get", side_effect=fake_get):
        with patch.object(kalshi, "BACKFILL_RETRY_BACKOFF_SECONDS", 0):
            kalshi.fetch_market_candles("T-1", 0, 60, historical=True, limiter=limiter)

    assert attempts["n"] == 2
    assert limiter.rate < 40.0


def test_flatten_candlestick_flattens_nested_price_fields():
    candle = {
        "end_period_ts": 123,
        "open_interest_fp": "2.00",
        "volume_fp": "1.00",
        "price": {},  # empty when no trade happened in this candle — confirmed directly
        "yes_bid": {"close_dollars": "0.40"},
        "yes_ask": {"close_dollars": "0.45"},
    }

    row = kalshi._flatten_candlestick("TICKER-1", candle)

    assert row["ticker"] == "TICKER-1"
    assert row["ts"] == 123
    assert row["open_interest"] == "2.00"
    assert row["volume"] == "1.00"
    assert row["yes_bid_close_dollars"] == "0.40"
    assert row["yes_ask_close_dollars"] == "0.45"
    assert "price_close_dollars" not in row
