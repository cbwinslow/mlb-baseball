"""Real DB, real DataFrame/COPY loading — only requests.get is mocked, via a
fake matching polymarket.fetch_events' keyset-pagination + filter-param
contract rather than patching the Gamma API responses verbatim."""

from unittest.mock import patch

import pytest

from mlb_baseball.connectors import polymarket

ALL_TABLES = [polymarket.EVENT_TABLE, polymarket.MARKET_TABLE, polymarket.OUTCOME_TABLE]


def _event(event_id, n_markets=1):
    return {
        "id": event_id,
        "title": f"Event {event_id}",
        "markets": [
            {
                "id": f"{event_id}-{i}",
                "question": f"Market {event_id}-{i}",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.5", "0.5"]',
                "clobTokenIds": '["tok-a", "tok-b"]',
            }
            for i in range(n_markets)
        ],
    }


def _page(events, next_cursor=None):
    """A single /events/keyset response — next_cursor is omitted from the
    dict entirely on the last page, matching the real API's confirmed shape."""
    payload = {"events": events}
    if next_cursor is not None:
        payload["next_cursor"] = next_cursor
    return payload


@pytest.fixture(autouse=True)
def _clean_tables(db_conn):
    yield
    with db_conn.cursor() as cur:
        for table in ALL_TABLES:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute("DELETE FROM meta.ingestion_run WHERE source = %s", (polymarket.SOURCE,))
    db_conn.commit()


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _no_results_get(url, params=None, timeout=None):
    return FakeResponse(_page([]))


def test_fetch_events_follows_next_cursor_until_omitted():
    pages = [
        _page([_event(str(i)) for i in range(polymarket.PAGE_SIZE)], next_cursor="cursor-1"),
        _page([_event(str(polymarket.PAGE_SIZE))]),  # no next_cursor key: last page
    ]
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(dict(params))
        return FakeResponse(pages.pop(0))

    with patch.object(polymarket.requests, "get", side_effect=fake_get):
        events = polymarket.fetch_events({"series_id": polymarket.MLB_SERIES_ID})

    assert len(events) == polymarket.PAGE_SIZE + 1
    assert "after_cursor" not in calls[0]
    assert calls[1]["after_cursor"] == "cursor-1"


def test_run_loads_event_market_and_outcome_tables(db_conn):
    def fake_get(url, params=None, timeout=None):
        if params.get("series_id") == polymarket.MLB_SERIES_ID and params.get("closed") == "false":
            return FakeResponse(_page([_event("1", n_markets=2)]))
        return _no_results_get(url, params, timeout)

    with patch.object(polymarket.requests, "get", side_effect=fake_get):
        counts = polymarket.bootstrap()

    assert counts[polymarket.EVENT_TABLE] == 1
    assert counts[polymarket.MARKET_TABLE] == 2
    assert counts[polymarket.OUTCOME_TABLE] == 4  # 2 markets x 2 outcomes each
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {polymarket.MARKET_TABLE}")
        assert cur.fetchone() == (2,)


def test_run_deduplicates_an_event_returned_by_both_queries(db_conn):
    # Regression: series_id=3 and tag_slug=mlb overlap heavily in production
    # (confirmed: ~5,554 of ~5,700 daily games also carry the "mlb" tag) —
    # without de-duping by event id, an overlapping event would be inserted
    # twice, once per query that returned it.
    shared_event = _event("1")

    def fake_get(url, params=None, timeout=None):
        if params.get("series_id") == polymarket.MLB_SERIES_ID and params.get("closed") == "false":
            return FakeResponse(_page([shared_event]))
        if params.get("tag_slug") == polymarket.MLB_TAG_SLUG:
            return FakeResponse(_page([shared_event]))
        return _no_results_get(url, params, timeout)

    with patch.object(polymarket.requests, "get", side_effect=fake_get):
        counts = polymarket.bootstrap()

    assert counts[polymarket.EVENT_TABLE] == 1
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {polymarket.EVENT_TABLE}")
        assert cur.fetchone() == (1,)


def test_rerunning_replaces_instead_of_duplicating(db_conn):
    def fake_get(url, params=None, timeout=None):
        if params.get("series_id") == polymarket.MLB_SERIES_ID and params.get("closed") == "false":
            return FakeResponse(_page([_event("1")]))
        return _no_results_get(url, params, timeout)

    with patch.object(polymarket.requests, "get", side_effect=fake_get):
        polymarket.bootstrap()
        polymarket.update()

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {polymarket.EVENT_TABLE}")
        assert cur.fetchone() == (1,)
        cur.execute(f"SELECT count(*) FROM {polymarket.MARKET_TABLE}")
        assert cur.fetchone() == (1,)


def test_run_handles_no_events_without_erroring(db_conn):
    with patch.object(polymarket.requests, "get", side_effect=_no_results_get):
        counts = polymarket.bootstrap()

    assert counts == dict.fromkeys(ALL_TABLES, 0)


def test_health_check_reports_last_run(db_conn):
    def fake_get(url, params=None, timeout=None):
        if params.get("series_id") == polymarket.MLB_SERIES_ID and params.get("closed") == "false":
            return FakeResponse(_page([_event("1")]))
        return _no_results_get(url, params, timeout)

    with patch.object(polymarket.requests, "get", side_effect=fake_get):
        polymarket.bootstrap()

    checks = polymarket.health_check()

    assert any(c.name == f"{polymarket.SOURCE} last run" for c in checks)
    assert all(c.ok for c in checks)
