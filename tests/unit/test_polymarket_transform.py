from unittest.mock import patch

import pytest

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


def test_fetch_batch_history_posts_one_request_and_returns_points_by_token():
    sent = []

    def fake_post(url, body):
        sent.append((url, body))
        return {"history": {"tok-1": [{"t": 1, "p": 0.5}], "tok-2": []}}

    with patch.object(polymarket, "_clob_post", side_effect=fake_post):
        history = polymarket.fetch_batch_history(["tok-1", "tok-2"], 100, 200)

    assert sent == [
        (
            f"{polymarket.CLOB_BASE_URL}/batch-prices-history",
            {"markets": ["tok-1", "tok-2"], "start_ts": 100, "end_ts": 200},
        )
    ]
    assert history == {"tok-1": [{"t": 1, "p": 0.5}], "tok-2": []}


def test_fetch_batch_history_refuses_more_tokens_than_the_api_accepts():
    too_many = [f"t{i}" for i in range(polymarket.BATCH_SIZE + 1)]
    with pytest.raises(ValueError, match="at most"):
        polymarket.fetch_batch_history(too_many, 0, 1)


def test_fetch_batch_history_slows_the_shared_limiter_on_429_then_retries():
    import requests

    from mlb_baseball.net import RateLimiter

    limiter = RateLimiter(50.0)
    calls = {"n": 0}

    def fake_post(url, body):
        calls["n"] += 1
        if calls["n"] == 1:
            reply = requests.Response()
            reply.status_code = 429
            reply.headers["Retry-After"] = "0"
            raise requests.exceptions.HTTPError(response=reply)
        return {"history": {}}

    with patch.object(polymarket, "_clob_post", side_effect=fake_post):
        with patch.object(polymarket, "BACKFILL_RETRY_BACKOFF_SECONDS", 0):
            assert polymarket.fetch_batch_history(["t"], 0, 1, limiter) == {}

    assert calls["n"] == 2
    assert limiter.rate < 50.0


def test_plan_batches_groups_tokens_by_window_newest_first_and_skips_done():
    window = polymarket.HISTORY_WINDOW_SECONDS
    now = 100 * window
    old, new = 10 * window + 5, 98 * window + 5
    tokens = [
        {
            "clob_token_id": f"a{i}",
            "_market": "m",
            "_event": "e",
            "start_ts": old,
            "end_ts": old + 60,
        }
        for i in range(25)
    ] + [
        {"clob_token_id": "b", "_market": "m", "_event": "e", "start_ts": new, "end_ts": None},
        {"clob_token_id": "x", "_market": "m", "_event": "e", "start_ts": None, "end_ts": None},
    ]
    done = {f"a0:{10 * window}"}

    batches, undated = polymarket._plan_batches(tokens, done, now)

    assert [t["clob_token_id"] for t in undated] == ["x"]
    cells = [cell for cell, _ in batches]
    assert cells == sorted(cells, reverse=True)  # newest window first
    assert all(len(group) <= polymarket.BATCH_SIZE for _, group in batches)
    old_ids = {t["clob_token_id"] for cell, g in batches if cell == 10 * window for t in g}
    assert "a0" not in old_ids and len(old_ids) == 24  # the ledgered one is skipped
    # an open market's windows from its start up to now: 98, 99 and 100
    assert [c // window for c, g in batches if any(t["clob_token_id"] == "b" for t in g)] == [
        100,
        99,
        98,
    ]


def test_plan_batches_refetches_a_window_that_is_still_recent_even_if_ledgered():
    window = polymarket.HISTORY_WINDOW_SECONDS
    now = 100 * window + 100
    token = {
        "clob_token_id": "b",
        "_market": "m",
        "_event": "e",
        "start_ts": now - 60,
        "end_ts": None,
    }
    cell = (now - 60) // window * window
    batches, _ = polymarket._plan_batches([token], {f"b:{cell}"}, now)
    assert [c for c, _ in batches] == [cell]


def test_csv_cell_quotes_only_when_needed():
    assert polymarket._csv_cell("12345") == "12345"
    assert polymarket._csv_cell("a,b") == '"a,b"'
    assert polymarket._csv_cell('say "hi"') == '"say ""hi"""'
