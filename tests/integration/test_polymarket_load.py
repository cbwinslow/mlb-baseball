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


# --- Fast batch backfill (odds-bulk-history section 3) --------------------


def _bootstrap_with(events):
    def fake_get(url, params=None, timeout=None):
        if params.get("series_id") == polymarket.MLB_SERIES_ID and params.get("closed") == "false":
            return FakeResponse(_page(events))
        return _no_results_get(url, params, timeout)

    with patch.object(polymarket.requests, "get", side_effect=fake_get):
        polymarket.bootstrap()


class FakeClob:
    """Behaves like the real batch endpoint: at most 20 tokens, windows over 15 days are
    rejected, a token with no points in the window is absent from the answer."""

    def __init__(self, points_by_token=None, fail_windows=()):
        self.points = points_by_token or {}
        self.fail_windows = set(fail_windows)
        self.calls = []

    def __call__(self, url, body):
        import requests

        self.calls.append(body)
        assert len(body["markets"]) <= 20
        assert body["end_ts"] - body["start_ts"] <= 15 * 86400
        if body["start_ts"] in self.fail_windows:
            raise requests.exceptions.ConnectionError("source went away")
        history = {}
        for token in body["markets"]:
            pts = [
                {"t": t, "p": p}
                for t, p in self.points.get(token, [])
                if body["start_ts"] <= t < body["end_ts"]
            ]
            if pts:
                history[token] = pts
        return {"history": history}


def _run_backfill(clob):
    with patch.object(polymarket, "_clob_post", side_effect=clob):
        with patch.object(polymarket, "BACKFILL_RETRY_BACKOFF_SECONDS", 0):
            return polymarket.backfill_history()


def _price_rows(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            f"SELECT clob_token_id, ts, price FROM {polymarket.PRICE_TABLE} ORDER BY 1, ts::bigint"
        )
        return cur.fetchall()


def _ledger(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT item_key, status, rows FROM meta.ingestion_item "
            "WHERE source = %s AND dataset = %s ORDER BY item_key",
            (polymarket.SOURCE, polymarket.PRICE_DATASET),
        )
        return cur.fetchall()


@pytest.fixture
def _ledger_clean(db_conn):
    yield
    with db_conn.cursor() as cur:
        cur.execute(
            "DELETE FROM meta.ingestion_item WHERE source = %s AND dataset = %s",
            (polymarket.SOURCE, polymarket.PRICE_DATASET),
        )
    db_conn.commit()


def test_backfill_loads_settled_market_history_by_window(db_conn, _ledger_clean):
    _bootstrap_with(
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
    t0 = polymarket._epoch("2025-04-02T09:00:00Z")
    clob = FakeClob({"tok-1-0-a": [(t0, 0.4), (t0 + 60, 0.45)], "tok-1-0-b": [(t0, 0.6)]})

    counts = _run_backfill(clob)

    assert counts[polymarket.PRICE_TABLE] == 3
    assert [r[0] for r in _price_rows(db_conn)] == ["tok-1-0-a", "tok-1-0-a", "tok-1-0-b"]
    assert len(clob.calls) == 1  # both tokens of the market share one request
    assert {s for _, s, _ in _ledger(db_conn)} == {"loaded"}


def test_backfill_remembers_empty_windows_and_skips_them_on_rerun(db_conn, _ledger_clean):
    _bootstrap_with(
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
    clob = FakeClob({})
    _run_backfill(clob)
    first_calls = len(clob.calls)
    _run_backfill(clob)

    assert first_calls == 1
    assert len(clob.calls) == first_calls  # nothing refetched
    assert {(s, r) for _, s, r in _ledger(db_conn)} == {("unavailable", 0)}


def test_backfill_rerun_replaces_a_window_instead_of_duplicating(db_conn, _ledger_clean):
    _bootstrap_with(
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
    t0 = polymarket._epoch("2025-04-02T09:00:00Z")
    clob = FakeClob({"tok-1-0-a": [(t0, 0.4)]})
    _run_backfill(clob)
    with db_conn.cursor() as cur:  # forget the ledger so the window is fetched again
        cur.execute(
            "DELETE FROM meta.ingestion_item WHERE dataset = %s", (polymarket.PRICE_DATASET,)
        )
    db_conn.commit()
    _run_backfill(clob)

    assert len(_price_rows(db_conn)) == 1


def test_backfill_keeps_other_windows_when_one_window_is_replaced(db_conn, _ledger_clean):
    window = polymarket.HISTORY_WINDOW_SECONDS
    start = polymarket._epoch("2026-06-01T00:00:00Z")
    _bootstrap_with(
        [
            _event(
                "1",
                closed=True,
                sport="mlb",
                startdate="2026-06-01T00:00:00Z",
                closedtime="2026-07-01 00:00:00+00",  # 30 days: three windows
            )
        ]
    )
    cell0 = start // window * window
    clob = FakeClob(
        {
            "tok-1-0-a": [
                (cell0 + 10, 0.1),
                (cell0 + window + 10, 0.2),
                (cell0 + 2 * window + 10, 0.3),
            ]
        }
    )

    _run_backfill(clob)

    assert [p for _, _, p in _price_rows(db_conn)] == ["0.1", "0.2", "0.3"]
    assert len({c["start_ts"] for c in clob.calls}) == 3


def test_backfill_processes_newest_window_first(db_conn, _ledger_clean):
    _bootstrap_with(
        [
            _event(
                "1",
                closed=True,
                sport="mlb",
                startdate="2025-04-02T08:02:33Z",
                closedtime="2025-04-02 21:25:34+00",
            ),
            _event(
                "2",
                closed=True,
                sport="mlb",
                startdate="2026-08-02T08:02:33Z",
                closedtime="2026-08-02 21:25:34+00",
            ),
        ]
    )
    clob = FakeClob({})
    with patch.object(polymarket, "BACKFILL_WORKERS", 1):
        _run_backfill(clob)
    starts = [c["start_ts"] for c in clob.calls]
    assert starts == sorted(starts, reverse=True)


def test_backfill_records_failures_keeps_going_and_a_rerun_retries_only_them(
    db_conn, _ledger_clean
):
    window = polymarket.HISTORY_WINDOW_SECONDS
    _bootstrap_with(
        [
            _event(
                "1",
                closed=True,
                sport="mlb",
                startdate="2025-04-02T08:02:33Z",
                closedtime="2025-04-02 21:25:34+00",
            ),
            _event(
                "2",
                closed=True,
                sport="mlb",
                startdate="2026-08-02T08:02:33Z",
                closedtime="2026-08-02 21:25:34+00",
            ),
        ]
    )
    bad = polymarket._epoch("2025-04-02T08:02:33Z") // window * window
    t_good = polymarket._epoch("2026-08-02T09:00:00Z")
    clob = FakeClob({"tok-2-0-a": [(t_good, 0.5)]}, fail_windows=[bad])

    with pytest.raises(RuntimeError, match="failed"):
        _run_backfill(clob)

    statuses = {k.split(":")[0]: s for k, s, _ in _ledger(db_conn)}
    assert statuses["tok-1-0-a"] == "failed"
    assert statuses["tok-2-0-a"] == "loaded"  # the other window still landed

    clob.fail_windows.clear()
    clob.calls.clear()
    _run_backfill(clob)
    assert {c["start_ts"] for c in clob.calls} == {bad}  # only the failed window retried
    assert {s for _, s, _ in _ledger(db_conn)} <= {"loaded", "unavailable"}


def test_backfill_marks_a_market_with_no_start_date_unavailable(db_conn, _ledger_clean):
    _bootstrap_with([_event("1", closed=True, sport="mlb", startdate=None, closedtime=None)])
    clob = FakeClob({})
    _run_backfill(clob)
    assert clob.calls == []
    assert {s for _, s, _ in _ledger(db_conn)} == {"unavailable"}


def test_backfill_reports_progress_and_timing_to_the_monitor(db_conn, _ledger_clean):
    _bootstrap_with(
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
    _run_backfill(FakeClob({}))
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT items_planned, items_done FROM meta.ingestion_run "
            "WHERE source = %s AND mode = 'backfill' ORDER BY id DESC LIMIT 1",
            (polymarket.SOURCE,),
        )
        assert cur.fetchone() == (1, 1)
        cur.execute("SELECT count(*) FROM meta.op_span WHERE op = 'polymarket.batch'")
        assert cur.fetchone()[0] >= 1
        cur.execute("DELETE FROM meta.op_span WHERE op = 'polymarket.batch'")
    db_conn.commit()
