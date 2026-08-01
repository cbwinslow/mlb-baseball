"""Real DB, real DataFrame/COPY loading — only requests.get is mocked, via a
fake matching polymarket.fetch_events' keyset-pagination + filter-param
contract rather than patching the Gamma API responses verbatim."""

from unittest.mock import patch

import pytest

from mlb_baseball.connectors import polymarket

ALL_TABLES = [polymarket.EVENT_TABLE, polymarket.MARKET_TABLE, polymarket.OUTCOME_TABLE]
# Tables this test file's fixtures might create, beyond ALL_TABLES above —
# dropped after every test regardless of which ones a given test actually
# touched (raw.polymarket_price only exists once backfill_history() runs).
_CLEANUP_TABLES = [*ALL_TABLES, polymarket.SNAPSHOT_TABLE, polymarket.PRICE_TABLE]


def _event(event_id, n_markets=1, closed=False, sport=None):
    return {
        "id": event_id,
        "title": f"Event {event_id}",
        "sport": sport,
        "markets": [
            {
                "id": f"{event_id}-{i}",
                "question": f"Market {event_id}-{i}",
                "outcomes": '["Yes", "No"]',
                "outcomePrices": '["0.5", "0.5"]',
                "clobTokenIds": f'["tok-{event_id}-{i}-a", "tok-{event_id}-{i}-b"]',
                "closed": closed,
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
        for table in _CLEANUP_TABLES:
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

    assert counts == {**dict.fromkeys(ALL_TABLES, 0), polymarket.SNAPSHOT_TABLE: 0}


def test_health_check_reports_last_run(db_conn):
    def fake_get(url, params=None, timeout=None):
        if params.get("series_id") == polymarket.MLB_SERIES_ID and params.get("closed") == "false":
            return FakeResponse(_page([_event("1")]))
        return _no_results_get(url, params, timeout)

    with patch.object(polymarket.requests, "get", side_effect=fake_get):
        polymarket.bootstrap()

    checks = {c.name: c for c in polymarket.health_check()}

    assert checks[f"{polymarket.SOURCE} last run"].ok
    assert checks[polymarket.EVENT_TABLE].ok
    assert checks[polymarket.MARKET_TABLE].ok
    assert checks[polymarket.OUTCOME_TABLE].ok
    # raw.polymarket_snapshot is guaranteed to exist after any bootstrap()/
    # update() run (same fix as raw.mlb_live_game — see _run()'s own
    # comment), even though this run had no open markets to append.
    assert checks[polymarket.SNAPSHOT_TABLE].ok
    # raw.polymarket_price only exists once backfill_history() has actually
    # been run at least once (an owner-triggered one-off, not part of
    # bootstrap()/update()) — correctly reported unhealthy here, not a
    # false negative.
    assert not checks[polymarket.PRICE_TABLE].ok


# --- Forward snapshots (ADR-047) ---------------------------------------


def test_run_appends_snapshot_only_for_open_markets(db_conn):
    def fake_get(url, params=None, timeout=None):
        if params.get("series_id") == polymarket.MLB_SERIES_ID and params.get("closed") == "false":
            return FakeResponse(_page([_event("1", closed=False), _event("2", closed=True)]))
        return _no_results_get(url, params, timeout)

    with patch.object(polymarket.requests, "get", side_effect=fake_get):
        counts = polymarket.bootstrap()

    # Event "1"'s market has 2 outcomes and is open; event "2" is closed and
    # skipped entirely.
    assert counts[polymarket.SNAPSHOT_TABLE] == 2
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {polymarket.SNAPSHOT_TABLE}")
        assert cur.fetchone() == (2,)


def test_run_snapshot_accumulates_across_runs(db_conn):
    # append-only: rerunning should ADD another point-in-time observation,
    # unlike the scoped-replace event/market/outcome tables.
    def fake_get(url, params=None, timeout=None):
        if params.get("series_id") == polymarket.MLB_SERIES_ID and params.get("closed") == "false":
            return FakeResponse(_page([_event("1", closed=False)]))
        return _no_results_get(url, params, timeout)

    with patch.object(polymarket.requests, "get", side_effect=fake_get):
        polymarket.bootstrap()
        polymarket.update()

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {polymarket.SNAPSHOT_TABLE}")
        assert cur.fetchone() == (4,)  # 2 outcomes x 2 runs


def test_snapshot_table_exists_even_with_no_open_markets(db_conn):
    # Regression precedent: raw.mlb_live_game needed the same fix (always
    # call append_dataframe, even with 0 rows) so its existence doesn't
    # depend on the coincidence of an open market at run time.
    with patch.object(polymarket.requests, "get", side_effect=_no_results_get):
        polymarket.bootstrap()

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {polymarket.SNAPSHOT_TABLE}")
        assert cur.fetchone() == (0,)


# --- Historical price backfill (ADR-047) --------------------------------
# fetch_price_history's own request/parsing contract is pure-logic-plus-
# mocked-HTTP (no DB) and is unit-tested in
# tests/unit/test_polymarket_transform.py instead — these cover the parts
# that actually touch Postgres.


def test_daily_game_tokens_scopes_to_events_with_sport_set(db_conn):
    def fake_get(url, params=None, timeout=None):
        if params.get("series_id") == polymarket.MLB_SERIES_ID and params.get("closed") == "false":
            return FakeResponse(
                _page(
                    [
                        _event("1", sport="mlb"),  # a real per-game event
                        _event("2", sport=None),  # not a game (e.g. a stray non-sport entry)
                    ]
                )
            )
        return _no_results_get(url, params, timeout)

    with patch.object(polymarket.requests, "get", side_effect=fake_get):
        polymarket.bootstrap()

    tokens = polymarket._daily_game_tokens(db_conn)

    assert {t["clob_token_id"] for t in tokens} == {"tok-1-0-a", "tok-1-0-b"}


def test_backfill_history_loads_price_points_scoped_by_token(db_conn):
    def fake_get(url, params=None, timeout=None):
        if params.get("series_id") == polymarket.MLB_SERIES_ID and params.get("closed") == "false":
            return FakeResponse(_page([_event("1", sport="mlb")]))
        return _no_results_get(url, params, timeout)

    with patch.object(polymarket.requests, "get", side_effect=fake_get):
        polymarket.bootstrap()

    def fake_clob_get(url, params=None, timeout=None):
        return FakeResponse({"history": [{"t": 100, "p": 0.4}, {"t": 200, "p": 0.45}]})

    with patch.object(polymarket.requests, "get", side_effect=fake_clob_get):
        counts = polymarket.backfill_history()

    assert counts[polymarket.PRICE_TABLE] == 4  # 2 tokens x 2 points each
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {polymarket.PRICE_TABLE}")
        assert cur.fetchone() == (4,)


def test_backfill_history_rerunning_replaces_instead_of_duplicating(db_conn):
    def fake_get(url, params=None, timeout=None):
        if params.get("series_id") == polymarket.MLB_SERIES_ID and params.get("closed") == "false":
            return FakeResponse(_page([_event("1", sport="mlb")]))
        return _no_results_get(url, params, timeout)

    with patch.object(polymarket.requests, "get", side_effect=fake_get):
        polymarket.bootstrap()

    def fake_clob_get(url, params=None, timeout=None):
        return FakeResponse({"history": [{"t": 100, "p": 0.4}]})

    with patch.object(polymarket.requests, "get", side_effect=fake_clob_get):
        polymarket.backfill_history()
        polymarket.backfill_history()

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {polymarket.PRICE_TABLE}")
        assert cur.fetchone() == (2,)  # 2 tokens x 1 point each, not doubled


def test_backfill_history_skips_tokens_with_no_history(db_conn):
    def fake_get(url, params=None, timeout=None):
        if params.get("series_id") == polymarket.MLB_SERIES_ID and params.get("closed") == "false":
            return FakeResponse(_page([_event("1", sport="mlb")]))
        return _no_results_get(url, params, timeout)

    with patch.object(polymarket.requests, "get", side_effect=fake_get):
        polymarket.bootstrap()

    def fake_clob_get(url, params=None, timeout=None):
        return FakeResponse({"history": []})

    with patch.object(polymarket.requests, "get", side_effect=fake_clob_get):
        counts = polymarket.backfill_history()

    assert counts[polymarket.PRICE_TABLE] == 0
