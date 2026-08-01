from unittest.mock import patch

from mlb_baseball.connectors import polymarket


def _market(market_id, outcomes=None, prices=None, token_ids=None, **extra):
    market = {"id": market_id, "question": f"Market {market_id}", **extra}
    if outcomes is not None:
        market["outcomes"] = outcomes
    if prices is not None:
        market["outcomePrices"] = prices
    if token_ids is not None:
        market["clobTokenIds"] = token_ids
    return market


def _event(event_id, markets, **extra):
    return {"id": event_id, "title": f"Event {event_id}", "markets": markets, **extra}


def test_flatten_events_produces_event_market_outcome_rows():
    events = [
        _event(
            "1",
            [
                _market(
                    "10",
                    outcomes='["Yes", "No"]',
                    prices='["0.6", "0.4"]',
                    token_ids='["tok-a", "tok-b"]',
                )
            ],
        )
    ]

    tables = polymarket.flatten_events(events)

    event_df = tables[polymarket.EVENT_TABLE]
    market_df = tables[polymarket.MARKET_TABLE]
    outcome_df = tables[polymarket.OUTCOME_TABLE]

    assert list(event_df["id"]) == ["1"]
    assert "markets" not in event_df.columns

    assert list(market_df["id"]) == ["10"]
    assert list(market_df["event_id"]) == ["1"]
    for nested_field in ("outcomes", "outcomePrices", "clobTokenIds"):
        assert nested_field not in market_df.columns

    assert len(outcome_df) == 2
    assert outcome_df.iloc[0].to_dict() == {
        "market_id": "10",
        "outcome": "Yes",
        "price": "0.6",
        "clob_token_id": "tok-a",
    }
    assert outcome_df.iloc[1].to_dict() == {
        "market_id": "10",
        "outcome": "No",
        "price": "0.4",
        "clob_token_id": "tok-b",
    }


def test_flatten_events_handles_a_market_with_no_outcomes_field():
    # Real shape confirmed from the live API: not every market necessarily
    # carries populated outcomes/outcomePrices/clobTokenIds fields.
    events = [_event("1", [_market("10")])]

    tables = polymarket.flatten_events(events)

    assert tables[polymarket.OUTCOME_TABLE].empty
    assert list(tables[polymarket.MARKET_TABLE]["id"]) == ["10"]


def test_flatten_events_handles_an_event_with_no_markets():
    events = [_event("1", [])]

    tables = polymarket.flatten_events(events)

    assert list(tables[polymarket.EVENT_TABLE]["id"]) == ["1"]
    assert tables[polymarket.MARKET_TABLE].empty
    assert tables[polymarket.OUTCOME_TABLE].empty


def test_outcome_rows_pairs_by_index_even_with_a_mismatched_length():
    # Defensive: if prices/token_ids ever come back shorter than outcomes
    # (not observed live, but the API gives no guarantee), missing entries
    # should be None, not raise an IndexError.
    market = _market(
        "10", outcomes='["Yes", "No", "Maybe"]', prices='["0.5", "0.3"]', token_ids='["tok-a"]'
    )

    rows = polymarket._outcome_rows(market)

    assert rows == [
        {"market_id": "10", "outcome": "Yes", "price": "0.5", "clob_token_id": "tok-a"},
        {"market_id": "10", "outcome": "No", "price": "0.3", "clob_token_id": None},
        {"market_id": "10", "outcome": "Maybe", "price": None, "clob_token_id": None},
    ]


def test_snapshot_rows_skips_closed_markets_and_stamps_captured_at():
    events = [
        _event(
            "1",
            [_market("10", outcomes='["Yes", "No"]', prices='["0.6", "0.4"]', closed=False)],
        ),
        _event(
            "2",
            [_market("20", outcomes='["Yes", "No"]', prices='["0.9", "0.1"]', closed=True)],
        ),
    ]

    rows = polymarket._snapshot_rows(events, "2026-08-01T00:00:00+00:00")

    assert len(rows) == 2  # only event "1"'s market, not the closed one
    assert all(r["market_id"] == "10" for r in rows)
    assert all(r["captured_at"] == "2026-08-01T00:00:00+00:00" for r in rows)


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_fetch_price_history_returns_points():
    def fake_get(url, params=None, timeout=None):
        assert url == f"{polymarket.CLOB_BASE_URL}/prices-history"
        assert params == {"market": "tok-1", "interval": "max"}
        return FakeResponse({"history": [{"t": 1, "p": 0.5}, {"t": 2, "p": 0.6}]})

    with patch.object(polymarket.requests, "get", side_effect=fake_get):
        history = polymarket.fetch_price_history("tok-1")

    assert history == [{"t": 1, "p": 0.5}, {"t": 2, "p": 0.6}]


def test_fetch_price_history_handles_empty_history_without_erroring():
    # Confirmed directly against the real CLOB API: a token with no
    # matching/tradeable market returns {"history": []} with a normal 200,
    # not a 404 — this must not be treated as an error.
    def fake_get(url, params=None, timeout=None):
        return FakeResponse({"history": []})

    with patch.object(polymarket.requests, "get", side_effect=fake_get):
        history = polymarket.fetch_price_history("tok-does-not-exist")

    assert history == []
