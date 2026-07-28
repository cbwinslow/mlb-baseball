from mlb_baseball.connectors import kalshi


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
