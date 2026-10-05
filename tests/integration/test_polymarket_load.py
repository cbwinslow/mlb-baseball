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


def _event(
    event_id,
    n_markets=1,
    closed=False,
    sport=None,
    startdate="2026-09-01T00:00:00Z",
    closedtime="2026-09-02 00:00:00+00",
):
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
                "startdate": startdate,
                "closedtime": closedtime,
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
    # The backfill table only exists after the owner-triggered backfill_history():
    # not having run it is reported as a state, not a missing-table defect.
    assert checks[polymarket.PRICE_TABLE].ok
    assert "not run" in checks[polymarket.PRICE_TABLE].detail


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


def test_event_absent_from_a_later_pull_is_kept(db_conn):
    """Catalog history: an event the source stops returning is not deleted."""

    def pull(events):
        def fake_get(url, params=None, timeout=None):
            if (
                params.get("series_id") == polymarket.MLB_SERIES_ID
                and params.get("closed") == "false"
            ):
                return FakeResponse(_page(events))
            return _no_results_get(url, params, timeout)

        with patch.object(polymarket.requests, "get", side_effect=fake_get):
            polymarket.update()

    pull([_event("1"), _event("2")])
    pull([_event("1")])

    with db_conn.cursor() as cur:
        for table in (polymarket.EVENT_TABLE, polymarket.MARKET_TABLE):
            cur.execute(f"SELECT count(*) FROM {table}")
            assert cur.fetchone() == (2,), table
        cur.execute(f"SELECT count(*) FROM {polymarket.OUTCOME_TABLE}")
        assert cur.fetchone() == (4,)


# --- Snapshot-only capture (odds-history-capture) --------------------------


def _snapshot_patch(events, calls):
    def fake_get(url, params=None, timeout=None):
        calls.append(dict(params or {}))
        if params.get("closed") == "false" or params.get("tag_slug"):
            return FakeResponse(_page(events))
        return _no_results_get(url, params, timeout)

    return patch.object(polymarket.requests, "get", side_effect=fake_get)


def test_snapshot_keeps_every_capture_with_its_own_time(db_conn):
    event = _event("1")
    with _snapshot_patch([event], []):
        polymarket.snapshot()
        event["markets"][0]["outcomePrices"] = '["0.7", "0.3"]'
        polymarket.snapshot()

    with db_conn.cursor() as cur:
        cur.execute(
            f"SELECT price FROM {polymarket.SNAPSHOT_TABLE} "
            "WHERE outcome = 'Yes' ORDER BY captured_at"
        )
        assert cur.fetchall() == [("0.5",), ("0.7",)]


def test_snapshot_reads_only_open_markets_and_leaves_the_catalog_alone(db_conn):
    calls = []
    with _snapshot_patch([_event("1")], calls):
        counts = polymarket.snapshot()

    assert counts[polymarket.SNAPSHOT_TABLE] == 2  # Yes + No
    assert not any(p.get("closed") == "true" for p in calls)
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (polymarket.EVENT_TABLE,))
        assert cur.fetchone() == (None,)


def test_snapshot_with_no_open_markets_succeeds_and_creates_the_table(db_conn):
    with _snapshot_patch([], []):
        counts = polymarket.snapshot()

    assert counts[polymarket.SNAPSHOT_TABLE] == 0
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {polymarket.SNAPSHOT_TABLE}")
        assert cur.fetchone() == (0,)


def test_backfill_history_resumes_after_an_interruption_without_duplicates(db_conn):
    def fake_get(url, params=None, timeout=None):
        if params.get("series_id") == polymarket.MLB_SERIES_ID and params.get("closed") == "false":
            return FakeResponse(_page([_event("1", n_markets=2, sport="mlb")]))
        return _no_results_get(url, params, timeout)

    with patch.object(polymarket.requests, "get", side_effect=fake_get):
        polymarket.bootstrap()

    def clob_get(fail_on):
        def fake(url, params=None, timeout=None):
            if fail_on and params["market"] == fail_on:
                raise RuntimeError("source went away")
            return FakeResponse({"history": [{"t": 100, "p": 0.4}]})

        return fake

    with patch.object(polymarket, "BACKFILL_SLEEP_SECONDS", 0):
        with patch.object(polymarket.requests, "get", side_effect=clob_get("tok-1-1-a")):
            with pytest.raises(RuntimeError):
                polymarket.backfill_history()
        with patch.object(polymarket.requests, "get", side_effect=clob_get(None)):
            polymarket.backfill_history()

    with db_conn.cursor() as cur:
        cur.execute(f"SELECT clob_token_id, count(*) FROM {polymarket.PRICE_TABLE} GROUP BY 1")
        rows = cur.fetchall()
    assert len(rows) == 4  # 2 markets x 2 outcomes
    assert all(n == 1 for _, n in rows)


def _clob_that_only_serves_windows(history_by_window=None):
    """The real CLOB returns an empty history for a settled market asked with
    `interval=max` (checked live 2026-10-05 on 2025 markets) and rejects a
    window longer than a few weeks. This fake behaves the same way."""
    calls = []

    def fake(url, params=None, timeout=None):
        calls.append(dict(params))
        if "startTs" not in params:
            return FakeResponse({"history": []})
        if params["endTs"] - params["startTs"] > 15 * 86400:
            return FakeResponse({"history": [], "error": "interval is too long"})
        return FakeResponse({"history": [{"t": params["startTs"] + 1, "p": 0.4}]})

    return fake, calls


def test_backfill_history_asks_for_the_market_s_own_dates_not_interval_max(db_conn):
    def fake_get(url, params=None, timeout=None):
        if params.get("series_id") == polymarket.MLB_SERIES_ID and params.get("closed") == "false":
            return FakeResponse(
                _page(
                    [
                        _event(
                            "1",
                            closed=True,
                            sport="mlb",
                            startdate="2025-04-02T08:02:33Z",
                            closedtime="2025-04-02 21:25:34+00",
                        )
                    ]
                )
            )
        return _no_results_get(url, params, timeout)

    with patch.object(polymarket.requests, "get", side_effect=fake_get):
        polymarket.bootstrap()

    fake_clob, calls = _clob_that_only_serves_windows()
    with patch.object(polymarket, "BACKFILL_SLEEP_SECONDS", 0):
        with patch.object(polymarket.requests, "get", side_effect=fake_clob):
            counts = polymarket.backfill_history()

    assert counts[polymarket.PRICE_TABLE] == 2  # one point for each of the 2 outcomes
    assert all("interval" not in c for c in calls)


def test_backfill_history_splits_a_long_market_into_short_windows(db_conn):
    def fake_get(url, params=None, timeout=None):
        if params.get("series_id") == polymarket.MLB_SERIES_ID and params.get("closed") == "false":
            return FakeResponse(
                _page(
                    [
                        _event(
                            "1",
                            closed=True,
                            sport="mlb",
                            startdate="2026-06-01T00:00:00Z",
                            closedtime="2026-07-01 00:00:00+00",  # 30 days
                        )
                    ]
                )
            )
        return _no_results_get(url, params, timeout)

    with patch.object(polymarket.requests, "get", side_effect=fake_get):
        polymarket.bootstrap()

    fake_clob, calls = _clob_that_only_serves_windows()
    with patch.object(polymarket, "BACKFILL_SLEEP_SECONDS", 0):
        with patch.object(polymarket.requests, "get", side_effect=fake_clob):
            polymarket.backfill_history()

    per_token = [c for c in calls if c["market"] == "tok-1-0-a"]
    assert len(per_token) == 3  # 30 days in windows of at most 14
    assert all(c["endTs"] - c["startTs"] <= 14 * 86400 for c in per_token)
    ordered = sorted(per_token, key=lambda c: c["startTs"])
    assert all(a["endTs"] == b["startTs"] for a, b in zip(ordered, ordered[1:], strict=False))
