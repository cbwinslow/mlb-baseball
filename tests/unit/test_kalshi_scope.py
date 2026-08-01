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


def test_fetch_candlesticks_chunks_the_time_range(monkeypatch):
    # Regression: a too-wide single request 400s with "max candlesticks:
    # 5000" (confirmed directly against the real API) — fetch_candlesticks
    # must split any [start_ts, end_ts] wider than CANDLE_CHUNK_MINUTES into
    # multiple requests, never sending one that's too wide.
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(dict(params))
        return FakeResponse(
            {
                "candlesticks": [
                    {
                        "end_period_ts": params["start_ts"] + 60,
                        "open_interest_fp": "0",
                        "price": {},
                        "volume_fp": "0",
                        "yes_bid": {},
                        "yes_ask": {},
                    }
                ]
            }
        )

    monkeypatch.setattr(kalshi.requests, "get", fake_get)
    chunk_seconds = kalshi.CANDLE_CHUNK_MINUTES * 60
    start_ts = 0
    end_ts = chunk_seconds * 2 + 100  # spans 3 chunks

    candles = kalshi.fetch_candlesticks("KXMLBGAME", "TICKER-1", start_ts, end_ts)

    assert len(calls) == 3
    assert calls[0]["start_ts"] == 0
    assert calls[0]["end_ts"] == chunk_seconds
    assert calls[1]["start_ts"] == chunk_seconds
    assert calls[1]["end_ts"] == chunk_seconds * 2
    assert calls[2]["end_ts"] == end_ts
    assert len(candles) == 3


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
