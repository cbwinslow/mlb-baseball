"""Lands Polymarket's MLB prediction-market data into raw.polymarket_event/
market/outcome, via the public Gamma API (gamma-api.polymarket.com) — no
auth required for read access, confirmed directly (every call below returns
real data with no API key or header).

Two overlapping groups of MLB markets, both discovered by calling the live
API directly rather than trusting docs alone (the docs don't enumerate
exact IDs/slugs):
- Daily per-game moneylines: `GET /series` (recurrence=daily) has an "MLB"
  series with id=3 — `GET /events?series_id=3` returns one event per game
  (e.g. "Tampa Bay Rays vs. New York Yankees"), each with a nested `markets`
  list (moneyline plus in-game props like extra-innings/first-five-innings
  spread — confirmed via `GET /sports/market-types`, which lists
  `baseball_*`-prefixed market types). Real per-game data goes back to
  2021: 5,543 closed + 154 open events confirmed by paginating to the
  actual end (see fetch_events' pagination note below — an earlier,
  wrong ~2,500 estimate came from a pagination bug that silently
  truncated results).
- Every other MLB-tagged market: `GET /events?tag_slug=mlb` — broader than
  just season-long futures (an earlier, wrong assumption): also covers
  postseason series props ("NLDS: Mets vs. Phillies Game 3"), draft props
  ("2026 MLB Draft: Player to be Drafted 10th Overall"), All-Star Game
  props, and the season futures (World Series champion, AL/NL MVP, AL/NL
  Cy Young). Confirmed to overlap heavily with the daily-game set above
  (~5,554 of ~5,700 daily games also carry the "mlb" tag) — `_run()`
  de-dupes by event id before loading so an event pulled by both queries
  doesn't land twice.
- Real totals after de-duping: 5,926 events, 64,003 markets, 128,006
  outcomes (confirmed by running the full pull, not estimated).

Every market's `outcomes`/`outcomePrices`/`clobTokenIds` fields are
JSON-encoded parallel arrays (confirmed via a real call: outcomes=["Yes",
"No"], outcomePrices=["0.135", "0.865"]) — exploded into one row per
outcome in raw.polymarket_outcome rather than kept as opaque JSON blobs,
consistent with how this project explodes other nested API shapes (e.g.
chadwick_tools.py's cwbox supplementary lists).

bootstrap() and update() are the same full reload (like
chadwick_register.py/retrosheet_reference.py) — total volume (5,926 events,
64K market rows) is comparable to other full-reload/full-table sources
already in this project (e.g. raw.retrosheet_teamstats' 501K rows), and
there's no natural per-season API filter to scope a partial reload against
anyway (confirmed: the events endpoint's start_date_min/max params, which
work on /markets, return nothing when applied to /events). Every run also
appends a current-price snapshot for still-OPEN markets into
raw.polymarket_snapshot (see ADR-049) — reusing the events payload this
same run already fetched, no extra API calls.

**ADR-049 reversed ADR-026's exclusion of intraday price history.** The
owner now wants full price-timeseries/line-movement history for an
oddstrader-style product, not just the current/settled probability. Two
pieces cover that:
- `backfill_history()` — one-off historical backfill via the CLOB API's
  `/prices-history` endpoint (confirmed live: `market=<clob_token_id>&
  interval=max` returns `{"history": [{"t": <unix_seconds>, "p": <price>},
  ...]}` — 926 real points pulled for one real settled moneyline token). Not
  run by bootstrap()/update() — an owner-triggered `mlb ingest polymarket
  --mode backfill`, expected to take hours across the ~126K MLB
  daily-game-market tokens (confirmed via a real SELECT against production:
  5,828 daily-recurrence events, 63,019 markets under them — moneyline plus
  in-game spreads/totals/player props — 126,032 distinct clob_token_ids).
  Season-futures/postseason-prop/draft-prop tokens (the tag_slug=mlb query's
  events, not the daily series_id=3 ones) are explicitly NOT covered by this
  backfill — a real, deliberate scope cut, not an oversight; see ADR-049's
  "Revisit if" for picking that up as a follow-up.
- Forward snapshots (above) keep the series current going forward without
  needing to re-run the backfill.
"""

import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

import pandas as pd
import psycopg
import requests

from mlb_baseball.db import get_connection
from mlb_baseball.health import (
    DAILY_FRESHNESS_THRESHOLD_MINUTES,
    Check,
    check_backfill_state,
    check_last_run,
    check_recent_run,
    check_snapshot_gaps,
    check_table_exists,
    check_table_has_rows,
)
from mlb_baseball.ingest import record_items, track_run
from mlb_baseball.load import (
    append_dataframe,
    ensure_table,
    replace_csv_range,
    upsert_dataframe,
)
from mlb_baseball.net import RateLimiter, call_with_retry
from mlb_baseball.opsmon import Monitor

SOURCE = "polymarket"
SNAPSHOT_MAX_GAP_MINUTES = 30  # twice the 15-minute capture interval
SNAPSHOT_SOURCE = "polymarket_snapshot"  # run-ledger/lock name for snapshot()
FRESHNESS_THRESHOLD_MINUTES = DAILY_FRESHNESS_THRESHOLD_MINUTES
BASE_URL = "https://gamma-api.polymarket.com"
CLOB_BASE_URL = "https://clob.polymarket.com"  # prices-history only, confirmed unauthenticated
MLB_SERIES_ID = 3  # confirmed via GET /series?recurrence=daily
MLB_TAG_SLUG = "mlb"  # season-long futures, confirmed via GET /events?tag_slug=mlb
PAGE_SIZE = 100
# Backfill speed settings, measured live 2026-10-05 (see backfill_history). The documented
# ceiling is 1,000 requests / 10 s = 100/s without a key; the pacer sits at 90/s. Throughput
# stops rising past about 8-16 concurrent requests (the server queues beyond that, and 32
# concurrent heavy requests timed out), so 12 workers. Override per run with
# MLB_POLYMARKET_WORKERS / MLB_POLYMARKET_MAX_RPS.
BACKFILL_WORKERS = 12
BACKFILL_MAX_RPS = 90
BACKFILL_TIMEOUT_SECONDS = 60
BACKFILL_RETRY_BACKOFF_SECONDS = 2.0
BATCH_SIZE = 20  # `POST /batch-prices-history` accepts at most 20 markets
# The API rejects a window of 30 days ("interval is too long") and accepts 15 (docs: at
# most 15); 14 days leaves a margin.
HISTORY_WINDOW_SECONDS = 14 * 86400
# A window that ended less than this long ago may still receive points: refetch it.
SETTLE_SECONDS = 86400
PRICE_DATASET = "price_history"
PRICE_COLUMNS = ["clob_token_id", "_market", "_event", "ts", "price"]
_thread_state = threading.local()
_open_connections: list[psycopg.Connection] = []
_open_connections_lock = threading.Lock()

logger = logging.getLogger(__name__)

EVENT_TABLE = "raw.polymarket_event"
MARKET_TABLE = "raw.polymarket_market"
OUTCOME_TABLE = "raw.polymarket_outcome"
ALL_TABLES = [EVENT_TABLE, MARKET_TABLE, OUTCOME_TABLE]
# Source key each catalog table is replaced by; rows for keys the source no
# longer returns are kept (catalog history).
_CATALOG_KEYS = {EVENT_TABLE: "id", MARKET_TABLE: "id", OUTCOME_TABLE: "market_id"}
SNAPSHOT_TABLE = "raw.polymarket_snapshot"
PRICE_TABLE = "raw.polymarket_price"

_NESTED_MARKET_FIELDS = {"outcomes", "outcomePrices", "clobTokenIds"}


def _get(url: str, params: dict) -> dict:
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_events(params: dict) -> list[dict]:
    """Paginates via /events/keyset (cursor-based), not plain /events'
    offset/limit pagination. Found the hard way, not from docs: offset
    pagination on /events rejects anything past ~2,000 with a 422
    ("offset too large, use /events/keyset for deeper pagination") — hit on
    the first real production bootstrap, since this project's MLB event
    history is bigger than that. /events/keyset returns
    {"events": [...], "next_cursor": "..."}, with next_cursor omitted (not
    present as a key) on the final page — confirmed directly."""
    events: list[dict] = []
    cursor: str | None = None
    while True:
        page_params = {**params, "limit": PAGE_SIZE}
        if cursor:
            page_params["after_cursor"] = cursor
        page = call_with_retry(_get, f"{BASE_URL}/events/keyset", page_params)
        events.extend(page["events"])
        cursor = page.get("next_cursor")
        if not cursor:
            break
    return events


def _outcome_rows(market: dict) -> list[dict]:
    labels = json.loads(market.get("outcomes") or "[]")
    prices = json.loads(market.get("outcomePrices") or "[]")
    token_ids = json.loads(market.get("clobTokenIds") or "[]")
    return [
        {
            "market_id": market["id"],
            "outcome": label,
            "price": prices[i] if i < len(prices) else None,
            "clob_token_id": token_ids[i] if i < len(token_ids) else None,
        }
        for i, label in enumerate(labels)
    ]


def flatten_events(events: list[dict]) -> dict[str, pd.DataFrame]:
    event_rows = []
    market_rows = []
    outcome_rows = []
    for event in events:
        markets = event.get("markets", [])
        event_rows.append({k: v for k, v in event.items() if k != "markets"})
        for market in markets:
            market_row = {k: v for k, v in market.items() if k not in _NESTED_MARKET_FIELDS}
            market_row["event_id"] = event.get("id")
            market_rows.append(market_row)
            outcome_rows.extend(_outcome_rows(market))
    return {
        EVENT_TABLE: pd.DataFrame(event_rows),
        MARKET_TABLE: pd.DataFrame(market_rows),
        OUTCOME_TABLE: pd.DataFrame(outcome_rows),
    }


def _snapshot_rows(events: list[dict], captured_at: str) -> list[dict]:
    """Current-price snapshot rows for still-OPEN markets only (see
    ADR-049) — reuses the events payload _run() already fetched this call,
    no extra API request. `market["closed"]` is a real JSON boolean here
    (this runs on the freshly-parsed API response, before load_dataframe's
    text-ification), unlike the "True"/"False" strings already-landed raw
    tables show. Scoping to open markets only keeps what gets appended to
    raw.polymarket_snapshot proportional to how many MLB markets are
    actually live right now, not the full historical catalog."""
    rows = []
    for event in events:
        for market in event.get("markets", []):
            if market.get("closed"):
                continue
            for outcome_row in _outcome_rows(market):
                rows.append({**outcome_row, "captured_at": captured_at})
    return rows


SNAPSHOT_COLUMNS = ["market_id", "outcome", "price", "clob_token_id", "captured_at"]


def _append_snapshot(conn: psycopg.Connection, events: list[dict]) -> int:
    """Forward snapshot (ADR-049): append-only, never replaced — every run's
    open-market prices stay meaningful as a point-in-time observation. Always
    calls append_dataframe, even with 0 rows on a day with no open markets, so
    raw.polymarket_snapshot's own existence doesn't depend on the coincidence of
    an open market at run time — same fix mlb_api.capture_live() already needed
    for raw.mlb_live_game."""
    captured_at = datetime.now(UTC).isoformat()
    snapshot_df = pd.DataFrame(_snapshot_rows(events, captured_at), columns=SNAPSHOT_COLUMNS)
    return append_dataframe(
        conn,
        SNAPSHOT_TABLE,
        snapshot_df,
        identity_columns=("market_id", "outcome", "captured_at"),
    )


def snapshot() -> dict[str, int]:
    """Price-only capture for the frequent odds-history job: reads open events
    only and appends to raw.polymarket_snapshot, never touching the catalog
    tables (the nightly update() owns those). Recorded under its own run-ledger
    source so a capture tick never collides with the nightly polymarket run."""
    with (
        get_connection() as conn,
        track_run(conn, SNAPSHOT_SOURCE, "snapshot", workflow=None) as result,
    ):
        all_events = fetch_events({"series_id": MLB_SERIES_ID, "closed": "false"}) + fetch_events(
            {"tag_slug": MLB_TAG_SLUG, "closed": "false"}
        )
        events = list({event["id"]: event for event in all_events}.values())
        counts = {SNAPSHOT_TABLE: _append_snapshot(conn, events)}
        conn.commit()
        result["rows"] = counts[SNAPSHOT_TABLE]
    return counts


def _run(mode: str) -> dict[str, int]:
    counts: dict[str, int] = dict.fromkeys(ALL_TABLES, 0)
    counts[SNAPSHOT_TABLE] = 0
    with get_connection() as conn, track_run(conn, SOURCE, mode) as result:
        all_events = (
            fetch_events({"series_id": MLB_SERIES_ID, "closed": "false"})
            + fetch_events({"series_id": MLB_SERIES_ID, "closed": "true"})
            + fetch_events({"tag_slug": MLB_TAG_SLUG})
        )
        # The series_id and tag_slug queries overlap heavily (confirmed: most
        # daily games also carry the "mlb" tag) — de-dupe by event id so an
        # event pulled by both queries doesn't land twice.
        events = list({event["id"]: event for event in all_events}.values())
        tables = flatten_events(events)
        for table, df in tables.items():
            if df.empty:
                continue
            counts[table] = upsert_dataframe(conn, table, df, key_column=_CATALOG_KEYS[table])

        counts[SNAPSHOT_TABLE] = _append_snapshot(conn, events)

        conn.commit()
        result["rows"] = sum(counts.values())
    return counts


def bootstrap() -> dict[str, int]:
    return _run("bootstrap")


def update() -> dict[str, int]:
    return _run("update")


def _clob_post(url: str, body: dict) -> dict:
    """POST to the CLOB API on this thread's own pooled session."""
    session = getattr(_thread_state, "session", None)
    if session is None:
        session = _thread_state.session = requests.Session()
    response = session.post(url, json=body, timeout=BACKFILL_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def fetch_batch_history(
    token_ids: list[str], start_ts: int, end_ts: int, limiter: RateLimiter | None = None
) -> dict[str, list[dict]]:
    """Price history for up to ``BATCH_SIZE`` outcome tokens over one window, in a
    single `POST /batch-prices-history`. Returns ``{token: [{"t": seconds, "p":
    price}, ...]}``; a token with no points in the window is absent or empty (a
    valid answer for a settled or never-traded market, not an error). A 429 slows
    the shared ``limiter`` down for every worker before the retry."""
    if len(token_ids) > BATCH_SIZE:
        raise ValueError(f"at most {BATCH_SIZE} tokens per request, got {len(token_ids)}")
    body = {"markets": token_ids, "start_ts": start_ts, "end_ts": end_ts}

    def post() -> dict:
        if limiter is not None:
            limiter.acquire()
        try:
            payload = _clob_post(f"{CLOB_BASE_URL}/batch-prices-history", body)
        except requests.exceptions.HTTPError as exc:
            reply = exc.response
            if limiter is not None and reply is not None and reply.status_code == 429:
                limiter.slow_down(float(reply.headers.get("Retry-After") or 1))
            raise
        if limiter is not None:
            limiter.speed_up()
        return payload

    post.__name__ = "batch-prices-history"
    return call_with_retry(post, backoff_seconds=BACKFILL_RETRY_BACKOFF_SECONDS).get("history", {})


def _epoch(value: str | None) -> int | None:
    """Unix seconds from a source timestamp text (`2025-04-02T08:02:33Z` or
    `2025-04-02 21:25:34+00`); None when the source gave none."""
    if not value:
        return None
    return int(datetime.fromisoformat(value).timestamp())


def _daily_game_tokens(conn: psycopg.Connection) -> list[dict]:
    """Enumerates every clob_token_id tied to a real MLB daily-game event —
    `e.sport IS NOT NULL` is the same signal conform.py's own
    `_polymarket_market_rows` uses to recognize a real per-game event (team
    data present, not a season-futures/postseason-prop/draft-prop entry).
    Confirmed directly against production: 5,828 daily-recurrence events,
    63,019 markets under them (moneyline plus in-game spread/total/
    player-prop markets, not just the game-winner line), 126,032 distinct
    outcome tokens — broader than just the ~8,700 moneyline-only tokens on
    purpose, since the owner's own direction (ADR-049) is maximum
    granularity for an oddstrader-style line-movement product."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT o.clob_token_id, m.id AS market_id, e.id AS event_id,
                   m.startdate, m.closedtime
            FROM raw.polymarket_event e
            JOIN raw.polymarket_market m ON m.event_id = e.id
            JOIN raw.polymarket_outcome o ON o.market_id = m.id
            WHERE e.sport IS NOT NULL
              AND o.clob_token_id IS NOT NULL AND o.clob_token_id <> ''
            ORDER BY m.id
            """
        )
        return [
            {
                "clob_token_id": token,
                "_market": market_id,
                "_event": event_id,
                "start_ts": _epoch(start),
                "end_ts": _epoch(closed),
            }
            for token, market_id, event_id, start, closed in cur.fetchall()
        ]


def _plan_batches(
    tokens: list[dict], done: set[str], now: int
) -> tuple[list[tuple[int, list[dict]]], list[dict]]:
    """Group tokens into (window start, up-to-``BATCH_SIZE`` tokens) requests, newest
    window first. A token's life is cut on a fixed grid of ``HISTORY_WINDOW_SECONDS``
    windows so tokens from different markets can share one request. A window already
    in the ledger is skipped unless it is still recent enough to receive new points.
    Tokens with no start date cannot be windowed and are returned separately."""
    by_cell: dict[int, list[dict]] = {}
    undated: list[dict] = []
    for token in tokens:
        if token["start_ts"] is None:
            undated.append(token)
            continue
        end = token["end_ts"] if token["end_ts"] is not None else now
        cell = token["start_ts"] // HISTORY_WINDOW_SECONDS * HISTORY_WINDOW_SECONDS
        while cell <= max(end, token["start_ts"]):
            settled = cell + HISTORY_WINDOW_SECONDS + SETTLE_SECONDS <= now
            if not (settled and f"{token['clob_token_id']}:{cell}" in done):
                by_cell.setdefault(cell, []).append(token)
            cell += HISTORY_WINDOW_SECONDS
    batches = [
        (cell, group[i : i + BATCH_SIZE])
        for cell, group in sorted(by_cell.items(), reverse=True)
        for i in range(0, len(group), BATCH_SIZE)
    ]
    return batches, undated


def _item(token: dict, cell: int, status: str, run_id: int, **extra: object) -> dict:
    return {
        "source": SOURCE,
        "dataset": PRICE_DATASET,
        "item_key": f"{token['clob_token_id']}:{cell}",
        "status": status,
        "run_id": run_id,
        **extra,
    }


def _backfill_batch(
    cell: int, group: list[dict], run_id: int, limiter: RateLimiter, monitor: Monitor
) -> tuple[int, int]:
    """Fetch one window for one group of tokens and land it, together with its ledger
    rows, in one transaction. Returns ``(rows, failed_tokens)``; a failed fetch is
    recorded per token and does not stop the run (a rerun retries it)."""
    conn = _thread_connection()
    token_ids = [t["clob_token_id"] for t in group]
    started = time.perf_counter()
    try:
        with monitor.timed("polymarket.batch", window=cell, tokens=len(group)) as op:
            history = fetch_batch_history(token_ids, cell, cell + HISTORY_WINDOW_SECONDS, limiter)
            lines: list[str] = []
            counts: dict[str, int] = {}
            for token in group:
                points = history.get(token["clob_token_id"])
                if not points:
                    continue
                prefix = ",".join(
                    _csv_cell(token[k]) for k in ("clob_token_id", "_market", "_event")
                )
                lines.extend(f"{prefix},{point['t']},{point['p']}\n" for point in points)
                counts[token["clob_token_id"]] = len(points)
            rows = replace_csv_range(
                conn,
                PRICE_TABLE,
                PRICE_COLUMNS,
                "".join(lines),
                key_column="clob_token_id",
                keys=token_ids,
                range_column="ts",
                low=cell,
                high=cell + HISTORY_WINDOW_SECONDS,
            )
            duration = round((time.perf_counter() - started) * 1000)
            record_items(
                conn,
                [
                    _item(
                        token,
                        cell,
                        "loaded" if counts.get(token["clob_token_id"]) else "unavailable",
                        run_id,
                        rows=int(counts.get(token["clob_token_id"], 0)),
                        http_status=200,
                        duration_ms=duration,
                    )
                    for token in group
                ],
            )
            conn.commit()
            op.rows, op.requests = rows, 1
            return rows, 0
    except Exception as exc:
        conn.rollback()
        logger.error("polymarket window %s (%d tokens) failed: %s", cell, len(group), exc)
        record_items(
            conn,
            [_item(token, cell, "failed", run_id, error=str(exc)[:500]) for token in group],
        )
        conn.commit()
        return 0, len(group)


def _csv_cell(value: object) -> str:
    """A CSV field, quoted only when it has to be (ids are plain digits in practice)."""
    text = str(value)
    if any(ch in text for ch in ',"\n\r'):
        return '"' + text.replace('"', '""') + '"'
    return text


def _thread_connection() -> psycopg.Connection:
    conn = getattr(_thread_state, "conn", None)
    if conn is None or conn.closed:
        conn = _thread_state.conn = get_connection()
        with _open_connections_lock:
            _open_connections.append(conn)
    return conn


def backfill_history() -> dict[str, int]:
    """Historical per-token price series, as fast as the CLOB API allows.

    Why it is built this way (measured 2026-10-05, openspec/changes/odds-bulk-history):
    ``interval=max`` returns nothing for a settled market, so history is asked for by
    explicit window; ``POST /batch-prices-history`` takes 20 tokens per request and the
    documented limit is 1,000 requests per 10 s without a key. A 20-token 14-day
    request takes about 0.3 s, and throughput stops improving past roughly 8-16
    concurrent requests (the server queues beyond that), so the work runs on
    ``BACKFILL_WORKERS`` threads, each with its own pooled HTTP session and database
    connection, paced by one shared ``RateLimiter`` set below the documented ceiling.

    Newest windows first. One ledger item per (token, window) is written in the same
    transaction as its rows, so a stopped run resumes exactly where it left off and an
    empty window is remembered rather than fetched again. Progress and per-request
    timing go to ``meta.run_progress`` / ``meta.op_span``. Windows that could still
    receive points (recent) are refetched every run. Raises at the end if any window
    failed, after trying all of them."""
    counts = {PRICE_TABLE: 0}
    workers = _env_int("MLB_POLYMARKET_WORKERS", BACKFILL_WORKERS)
    limiter = RateLimiter(float(os.environ.get("MLB_POLYMARKET_MAX_RPS", BACKFILL_MAX_RPS)))
    with get_connection() as conn, track_run(conn, SOURCE, "backfill") as result:
        run_id = result["run_id"]
        tokens = _daily_game_tokens(conn)
        ensure_table(
            conn,
            PRICE_TABLE,
            PRICE_COLUMNS,
            index_column="clob_token_id",
        )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT item_key FROM meta.ingestion_item "
                "WHERE source = %s AND dataset = %s AND status IN ('loaded', 'unavailable')",
                (SOURCE, PRICE_DATASET),
            )
            done = {key for (key,) in cur.fetchall()}
        batches, undated = _plan_batches(tokens, done, int(time.time()))
        if undated:
            record_items(
                conn,
                [
                    _item(
                        t,
                        0,
                        "unavailable",
                        run_id,
                        error="market has no start date, so no window can be requested",
                    )
                    for t in undated
                ],
            )
            conn.commit()
        logger.info(
            "polymarket backfill: %d tokens, %d requests planned, %d workers, up to %.0f/s",
            len(tokens),
            len(batches),
            workers,
            limiter.rate,
        )
        monitor = Monitor(run_id=run_id)
        total = failed = finished = 0
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [
                    pool.submit(_backfill_batch, cell, group, run_id, limiter, monitor)
                    for cell, group in batches
                ]
                try:
                    for future in as_completed(futures):
                        rows, bad = future.result()
                        total, failed, finished = total + rows, failed + bad, finished + 1
                        monitor.progress(done=finished, planned=len(batches), requests=finished)
                except BaseException:
                    for future in futures:
                        future.cancel()
                    raise
        finally:
            monitor.finish()
            monitor.close()
            _close_thread_connections()
        counts[PRICE_TABLE] = total
        result["rows"] = total
        if failed:
            raise RuntimeError(
                f"{failed} Polymarket token windows failed (recorded as failed in "
                "meta.ingestion_item); rerun the backfill to retry them"
            )
    return counts


def _close_thread_connections() -> None:
    with _open_connections_lock:
        for conn in _open_connections:
            if not conn.closed:
                conn.close()
        _open_connections.clear()


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


def health_check() -> list[Check]:
    return [
        check_table_has_rows(EVENT_TABLE),
        check_table_has_rows(MARKET_TABLE),
        check_table_has_rows(OUTCOME_TABLE),
        # Sparse-by-design (see check_table_exists) — raw.polymarket_snapshot
        # is only populated while at least one MLB market is currently open,
        # and raw.polymarket_price only after backfill_history() has been
        # run at least once (an owner-triggered one-off, not bootstrap()/
        # update()) — 0 rows on a fresh DB isn't unhealthy for either.
        check_table_exists(SNAPSHOT_TABLE),
        # Only exists after the owner-triggered backfill: "not run" is a state.
        check_backfill_state(PRICE_TABLE),
        # odds-history-capture: a price snapshot every 15 minutes on game days.
        check_snapshot_gaps(SNAPSHOT_TABLE, max_gap_minutes=SNAPSHOT_MAX_GAP_MINUTES),
        check_last_run(SOURCE),
        # mode="update" -- the daily-cron-scheduled mode. Unscoped, a manual
        # backfill_history() run (mode="backfill") would mask a genuinely
        # stale daily update, the same blind spot this check exists to close.
        check_recent_run(SOURCE, FRESHNESS_THRESHOLD_MINUTES, mode="update"),
    ]
