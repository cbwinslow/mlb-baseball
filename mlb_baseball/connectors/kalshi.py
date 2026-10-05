"""Lands Kalshi's MLB prediction-market data into raw.kalshi_series/event/
market, via the public REST API (api.elections.kalshi.com/trade-api/v2) —
no authentication needed for read-only market data, confirmed directly
(every call below succeeds with zero auth headers). This matters because
docs.kalshi.com's own "making authenticated requests" guide describes a
much heavier scheme (RSA-PSS-signed requests using KALSHI-ACCESS-KEY/
-SIGNATURE/-TIMESTAMP headers and a private key) — that signing
requirement is for trading/portfolio actions, not public market-data
reads, confirmed by calling GET /series, /events, /markets with no headers
at all and getting real 200 responses back. KALSHI_API_KEY (added to
.env for this connector) isn't actually used here as a result — kept for
a possible future authenticated feature, not required for what's built.

Every baseball-tagged series discovered via `GET /series?category=Sports&
tags=Baseball` (199 total, confirmed directly), then filtered down to true
MLB series by title — this project's scope is MLB specifically, not every
baseball league Kalshi lists markets for. EXCLUDED_SERIES_TICKERS below is
every series checked and excluded, each confirmed by reading its actual
title, not guessed from its ticker: KBO (Korea Baseball Organization), the
Mexican Baseball League, MiLB (explicitly sub-MLB), NCAA college baseball
and softball, NPB (Nippon Professional Baseball, Japan), the World
Baseball Classic (international tournament, not MLB), a congressional
charity game, and one series whose own title is literally "DO NOT USE"
(Kalshi's own deprecation marker). Everything else stays in — game
moneylines, spreads, totals, first-N-innings variants, per-team season win
totals, player props (HRs/hits/RBIs/strikeouts/stolen bases/total bases),
season stat leaders, every major award (MVP/Cy Young/Rookie of the Year/
Manager of the Year/Gold Glove/Silver Slugger/Comeback Player/Reliever of
the Year, AL and NL separately), division/league/World Series champions,
the draft, coaching changes, Home Run Derby, All-Star Game props, and a
couple of one-off player-specific markets — matching this session's
"ingest everything available" direction (ADR-020), not a curated subset.

Each Kalshi "market" (e.g. KXMLBGAME-26JUL311420NYYCHC-NYY) is already the
atomic yes/no contract with its own live price fields (yes_bid_dollars,
yes_ask_dollars, last_price_dollars, etc. — confirmed on a real market) —
unlike polymarket.py, there's no separate outcomes array to explode into a
fourth table; raw.kalshi_market is already the leaf level.

Historical depth is genuinely shallow, confirmed directly: KXMLBGAME
(daily game moneylines) only goes back to 2026-05-22 — Kalshi's sports
event-contract markets are new, not a years-deep archive like Polymarket's.

bootstrap()/update() are the same full reload (same reasoning as
polymarket.py/chadwick_register.py) — every status (open/closed/settled)
comes back in one paginated pull per series (confirmed: omitting the
`status` filter returns a mix, not just active markets), and there's no
per-season API filter to scope a partial reload against. Every run also
appends a current-price snapshot for still-active MLB markets into
raw.kalshi_snapshot (see ADR-049) — reusing the markets payload this same
run already fetched, no extra API calls.

**ADR-049 added intraday price history for Kalshi too** (the owner wants
full price-timeseries/line-movement depth for an oddstrader-style product):
- `backfill_history()` — one-off historical backfill via Kalshi's
  candlesticks endpoints (`GET /series/{series_ticker}/markets/{ticker}/
  candlesticks`, and `/historical/markets/{ticker}/candlesticks` for markets
  settled before `GET /historical/cutoff`), confirmed working unauthenticated
  directly, same as every other endpoint here. Covers every landed MLB market
  (it was `KXMLBGAME` only, and the catalog held only post-cutoff markets: the
  "2026-05-22" start in the note above was an artifact of that, Kalshi's game
  markets go back to 2025-04-16). Confirmed the endpoint rejects a request spanning too many
  candles at a given granularity with a plain 400 ("max candlesticks:
  5000") — `fetch_market_candles()` chunks the requested time range so no
  single call can hit that ceiling, rather than picking a coarser
  granularity and losing detail.
- Forward snapshots (above) keep the series current going forward.
"""

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
    replace_dataframe_scopes,
    upsert_dataframe,
)
from mlb_baseball.net import RateLimiter, call_with_retry
from mlb_baseball.opsmon import Monitor

logger = logging.getLogger(__name__)

SOURCE = "kalshi"
SNAPSHOT_MAX_GAP_MINUTES = 30  # twice the 15-minute capture interval
SNAPSHOT_SOURCE = "kalshi_snapshot"  # run-ledger/lock name for snapshot(); see snapshot()
FRESHNESS_THRESHOLD_MINUTES = DAILY_FRESHNESS_THRESHOLD_MINUTES
BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
# /markets accepts up to 1000 (confirmed directly); /events rejects anything
# above ~200-300 with a plain 400 (confirmed directly: 200 works, 300+
# doesn't) — no error detail given, and not documented, so a conservative
# confirmed-safe value is used rather than searching for the exact ceiling.
MARKETS_PAGE_SIZE = 1000
EVENTS_PAGE_SIZE = 200

SERIES_TABLE = "raw.kalshi_series"
EVENT_TABLE = "raw.kalshi_event"
MARKET_TABLE = "raw.kalshi_market"
ALL_TABLES = [SERIES_TABLE, EVENT_TABLE, MARKET_TABLE]
SNAPSHOT_TABLE = "raw.kalshi_snapshot"
CANDLE_TABLE = "raw.kalshi_candle"

BACKFILL_SOURCE = "kalshi_backfill"  # own run-ledger/lock name (see polymarket.BACKFILL_SOURCE)
CANDLE_DATASET = "candles"
# Maximum available granularity (1-minute candles). The endpoint rejects a request for more
# than 5,000 candles with a 400 (confirmed directly), so a market's life is cut into windows.
CANDLE_PERIOD_INTERVAL_MINUTES = 1
CANDLE_CHUNK_MINUTES = 4000
# Backfill speed. Kalshi's Basic tier allows 200 read tokens/s and most requests cost 10
# (docs.kalshi.com/getting_started/rate_limits), i.e. 20 requests/s; the pacer sits at 16/s
# (it halves on a 429). Workers: a candle request takes a few tenths of a second, so 8
# workers keep the pacer saturated. Override per run with MLB_KALSHI_WORKERS /
# MLB_KALSHI_MAX_RPS; raise them only with a new measurement.
BACKFILL_WORKERS = 8
BACKFILL_MAX_RPS = 16
BACKFILL_RETRY_BACKOFF_SECONDS = 2.0
# A market that closed less than this long ago may still be settling: refetch it.
SETTLE_SECONDS = 86400
_CANDLE_BASE_COLUMNS = ["ticker", "ts", "open_interest", "volume"]
_thread_state = threading.local()
_open_connections: list[psycopg.Connection] = []
_open_connections_lock = threading.Lock()
_schema_lock = threading.Lock()
_known_candle_columns: set[str] = set()

# Confirmed by reading each series' actual title (see module docstring) —
# not every "Baseball"-tagged Kalshi series is Major League Baseball.
EXCLUDED_SERIES_TICKERS = {
    # Korea Baseball Organization
    "KXKBOGAME",
    "KXKBO",
    "KXKBORFI",
    "KXKBOSPREAD",
    "KXKBOTOTAL",
    # Mexican Baseball League
    "KXLMBGAME",
    # Minor League Baseball — explicitly sub-MLB
    "KXMILBGAME",
    # NCAA college baseball
    "KXNCAABASEBALL",
    "KXNCAABBCONF",
    "KXNCAABBFINAL",
    "KXNCAABBGAME",
    "KXNCAABBGS",
    "KXNCAABBHR",
    "KXNCAABBPLAYOFFS",
    "KXNCAABBREG",
    "KXNCAABBSPREAD",
    "KXNCAABBTOTAL",
    "KXNCAAMBACHAMP",
    "KXTEAMSINNCAABBWS",
    # NCAA college softball — a different sport
    "KXNCAASBGAME",
    "KXNCAASOFTBALL",
    # Nippon Professional Baseball (Japan)
    "KXNPBGAME",
    "KXNPB",
    "KXNPBRFI",
    "KXNPBSPREAD",
    "KXNPBTOTAL",
    # World Baseball Classic — international tournament, not MLB
    "KXWBCF5",
    "KXWBCF5SPREAD",
    "KXWBCF5TOTAL",
    "KXWBCGAME",
    "KXWBCGROUPQUAL",
    "KXWBCGROUP",
    "KXWBCHIT",
    "KXWBCHR",
    "KXWBCKS",
    "KXWBCMVP",
    "KXWBCPREPACK",
    "KXWBCRFI",
    "KXWBCROUND",
    "KXWBCSPREAD",
    "KXWBCTOTAL",
    "KXMLBWORLD",
    # Congressional charity game, not real MLB
    "KXCONGRESSBASEBALL",
    # Kalshi's own title for this series is literally "DO NOT USE"
    "KXNLMOTY",
}


def _get(url: str, params: dict) -> dict:
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_series() -> list[dict]:
    payload = call_with_retry(
        _get,
        f"{BASE_URL}/series",
        {"category": "Sports", "tags": "Baseball", "limit": MARKETS_PAGE_SIZE},
    )
    return [s for s in payload["series"] if s["ticker"] not in EXCLUDED_SERIES_TICKERS]


def _paginate(
    path: str, series_ticker: str, result_key: str, page_size: int, extra_params: dict
) -> list[dict]:
    items: list[dict] = []
    cursor: str | None = None
    while True:
        params = {"series_ticker": series_ticker, "limit": page_size, **extra_params}
        if cursor:
            params["cursor"] = cursor
        page = call_with_retry(_get, f"{BASE_URL}{path}", params)
        items.extend(page[result_key])
        cursor = page.get("cursor")
        if not cursor:
            break
    return items


def fetch_events(series_ticker: str) -> list[dict]:
    return _paginate("/events", series_ticker, "events", EVENTS_PAGE_SIZE, {})


def fetch_markets(series_ticker: str, *, open_only: bool = False) -> list[dict]:
    params = {"mve_filter": "exclude", **({"status": "open"} if open_only else {})}
    return _paginate("/markets", series_ticker, "markets", MARKETS_PAGE_SIZE, params)


def fetch_cutoff() -> dict:
    """``GET /historical/cutoff``: markets and candlesticks settled before
    ``market_settled_ts`` are served only by the ``/historical`` endpoints; the live
    ``/markets`` listing no longer returns them (docs.kalshi.com, checked live
    2026-10-05: cutoff 2026-08-06)."""
    return call_with_retry(_get, f"{BASE_URL}/historical/cutoff", {})


def fetch_historical_markets(series_ticker: str) -> list[dict]:
    """Settled markets older than the cutoff (same fields as the live listing)."""
    return _paginate("/historical/markets", series_ticker, "markets", MARKETS_PAGE_SIZE, {})


_SNAPSHOT_FIELDS = [
    "ticker",
    "event_ticker",
    "status",
    "yes_bid_dollars",
    "yes_ask_dollars",
    "last_price_dollars",
    "volume_fp",
    "open_interest_fp",
]


def _snapshot_rows(markets: list[dict], captured_at: str) -> list[dict]:
    """Current-price snapshot for still-active MLB markets only (see
    ADR-049) — reuses the markets payload _run() already fetched this call,
    no extra API request. Keeps what gets appended to raw.kalshi_snapshot
    proportional to how many markets are actually active right now, not
    Kalshi's full historical catalog. Field subset mirrors raw.kalshi_market's
    own already-landed column names verbatim (source-faithful, not
    invented)."""
    rows = []
    for market in markets:
        if market.get("status") != "active":
            continue
        row = {field: market.get(field) for field in _SNAPSHOT_FIELDS}
        row["captured_at"] = captured_at
        rows.append(row)
    return rows


SNAPSHOT_COLUMNS = [*_SNAPSHOT_FIELDS, "captured_at"]


def _append_snapshot(conn: psycopg.Connection, markets: list[dict]) -> int:
    """Forward snapshot (ADR-049): append-only, never replaced — every run's
    active-market prices stay meaningful as a point-in-time observation, not
    just the latest one. Always calls append_dataframe, even with 0 rows on a
    run with no active markets, so raw.kalshi_snapshot's own existence doesn't
    depend on the coincidence of an active market at run time — same fix
    mlb_api.capture_live() already needed for raw.mlb_live_game."""
    captured_at = datetime.now(UTC).isoformat()
    snapshot_df = pd.DataFrame(_snapshot_rows(markets, captured_at), columns=SNAPSHOT_COLUMNS)
    count = append_dataframe(
        conn, SNAPSHOT_TABLE, snapshot_df, identity_columns=("ticker", "captured_at")
    )
    conn.commit()
    return count


def snapshot() -> dict[str, int]:
    """Price-only capture for the frequent odds-history job: reads open markets
    only and appends to raw.kalshi_snapshot. It never touches the catalog tables
    (series/event/market), which the nightly update() owns. Recorded under its
    own run-ledger source so a capture tick never collides with the nightly
    kalshi run's source lock."""
    with (
        get_connection() as conn,
        track_run(conn, SNAPSHOT_SOURCE, "snapshot", workflow=None) as result,
    ):
        markets: list[dict] = []
        failed: list[str] = []
        series = fetch_series()
        for s in series:
            try:
                markets.extend(fetch_markets(s["ticker"], open_only=True))
            except Exception as exc:
                logger.error("kalshi: %s snapshot failed (%s); continuing", s["ticker"], exc)
                failed.append(s["ticker"])
        if series and len(failed) == len(series):
            raise RuntimeError(f"kalshi snapshot: every series failed ({', '.join(failed)})")
        counts = {SNAPSHOT_TABLE: _append_snapshot(conn, markets)}
        result["rows"] = counts[SNAPSHOT_TABLE]
    return counts


def _run(mode: str) -> dict[str, int]:
    counts: dict[str, int] = dict.fromkeys(ALL_TABLES, 0)
    counts[SNAPSHOT_TABLE] = 0
    with get_connection() as conn, track_run(conn, SOURCE, mode) as result:
        series = fetch_series()
        if series:
            counts[SERIES_TABLE] = upsert_dataframe(
                conn, SERIES_TABLE, pd.DataFrame(series), key_column="ticker"
            )
            conn.commit()

        all_events: list[dict] = []
        all_markets: list[dict] = []
        for s in series:
            ticker = s["ticker"]
            try:
                all_events.extend(fetch_events(ticker))
                live = fetch_markets(ticker)
                all_markets.extend(live)
                # Markets settled before Kalshi's cutoff are only in the historical listing.
                seen = {m["ticker"] for m in live}
                all_markets.extend(
                    m for m in fetch_historical_markets(ticker) if m["ticker"] not in seen
                )
            except Exception as exc:
                logger.error("kalshi: %s failed (%s); skipping, continuing bootstrap", ticker, exc)

        if all_events:
            counts[EVENT_TABLE] = upsert_dataframe(
                conn, EVENT_TABLE, pd.DataFrame(all_events), key_column="event_ticker"
            )
            conn.commit()
        if all_markets:
            counts[MARKET_TABLE] = upsert_dataframe(
                conn, MARKET_TABLE, pd.DataFrame(all_markets), key_column="ticker"
            )
            conn.commit()

        counts[SNAPSHOT_TABLE] = _append_snapshot(conn, all_markets)

        result["rows"] = sum(counts.values())
    return counts


def bootstrap() -> dict[str, int]:
    return _run("bootstrap")


def update() -> dict[str, int]:
    return _run("update")


def _candle_get(url: str, params: dict) -> dict:
    """GET on this thread's own pooled HTTP session."""
    session = getattr(_thread_state, "session", None)
    if session is None:
        session = _thread_state.session = requests.Session()
    response = session.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_market_candles(
    ticker: str,
    start_ts: int,
    end_ts: int,
    *,
    historical: bool,
    limiter: RateLimiter | None = None,
) -> list[dict]:
    """1-minute candlesticks for one market over ``[start_ts, end_ts]``, cut into windows
    of at most ``CANDLE_CHUNK_MINUTES``. A market settled before the cutoff is read from
    ``/historical/markets/{ticker}/candlesticks``, any other from
    ``/series/{series}/markets/{ticker}/candlesticks``; if the chosen endpoint answers 404
    the other one is tried (the cutoff moves, and a market near it can be on either side).
    A 429 slows the shared ``limiter`` before the retry."""
    series = ticker.split("-")[0]
    paths = [
        f"/historical/markets/{ticker}/candlesticks",
        f"/series/{series}/markets/{ticker}/candlesticks",
    ]
    if not historical:
        paths.reverse()

    def get(path: str, params: dict) -> dict:
        if limiter is not None:
            limiter.acquire()
        try:
            payload = _candle_get(f"{BASE_URL}{path}", params)
        except requests.exceptions.HTTPError as exc:
            reply = exc.response
            if limiter is not None and reply is not None and reply.status_code == 429:
                limiter.slow_down(float(reply.headers.get("Retry-After") or 1))
            raise
        if limiter is not None:
            limiter.speed_up()
        return payload

    get.__name__ = "candlesticks"
    candles: list[dict] = []
    chunk_seconds = CANDLE_CHUNK_MINUTES * 60
    chunk_start = start_ts
    while chunk_start < end_ts:
        chunk_end = min(chunk_start + chunk_seconds, end_ts)
        params = {
            "start_ts": chunk_start,
            "end_ts": chunk_end,
            "period_interval": CANDLE_PERIOD_INTERVAL_MINUTES,
        }
        for index, path in enumerate(paths):
            try:
                payload = call_with_retry(
                    get, path, params, backoff_seconds=BACKFILL_RETRY_BACKOFF_SECONDS
                )
                break
            except requests.exceptions.HTTPError as exc:
                if index == 0 and exc.response is not None and exc.response.status_code == 404:
                    continue
                raise
        candles.extend(payload.get("candlesticks", []))
        chunk_start = chunk_end
    return candles


def _flatten_candlestick(ticker: str, candle: dict) -> dict:
    """Flattens one candlestick's nested price/yes_bid/yes_ask sub-objects
    into a flat row, prefixed by their own source field name (e.g.
    yes_bid_close_dollars) — source-faithful, not invented. `price` comes
    back as an empty dict `{}` on a candle with no trades (confirmed
    directly) — that just means fewer keys on this particular row, which
    pandas.DataFrame handles the same way this project already tolerates
    schema drift elsewhere (missing values, not a special case)."""
    row: dict = {
        "ticker": ticker,
        "ts": candle.get("end_period_ts"),
        "open_interest": candle.get("open_interest_fp"),
        "volume": candle.get("volume_fp"),
    }
    for prefix in ("price", "yes_bid", "yes_ask"):
        for field, value in (candle.get(prefix) or {}).items():
            row[f"{prefix}_{field}"] = value
    return row


def _parse_kalshi_ts(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def _candle_markets(conn: psycopg.Connection) -> list[dict]:
    """Every landed market that has a start and an end, game-level series before player-prop
    series (smaller series first, so the lines most useful for game models land first),
    newest market first within a series."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.ticker, m.open_time, m.close_time, m.settlement_ts
            FROM raw.kalshi_market m
            WHERE m.open_time IS NOT NULL AND m.close_time IS NOT NULL
            """
        )
        rows = cur.fetchall()
    markets = [
        {"ticker": t, "open_time": o, "close_time": c, "settlement_ts": st} for t, o, c, st in rows
    ]
    size: dict[str, int] = {}
    for market in markets:
        series = market["ticker"].split("-")[0]
        size[series] = size.get(series, 0) + 1
    markets.sort(key=lambda m: m["close_time"], reverse=True)
    markets.sort(key=lambda m: size[m["ticker"].split("-")[0]])
    return markets


def _candle_item(ticker: str, status: str, run_id: int, **extra: object) -> dict:
    return {
        "source": SOURCE,
        "dataset": CANDLE_DATASET,
        "item_key": ticker,
        "status": status,
        "run_id": run_id,
        **extra,
    }


def _thread_connection() -> psycopg.Connection:
    conn = getattr(_thread_state, "conn", None)
    if conn is None or conn.closed:
        conn = _thread_state.conn = get_connection()
        # Rows and their ledger row commit together and a rerun redoes any market without
        # a ledger row, so a crash can lose a few commits but never split a market from its
        # ledger entry (same reasoning as polymarket.backfill_history).
        with conn.cursor() as cur:
            cur.execute("SET synchronous_commit = off")
        conn.commit()
        with _open_connections_lock:
            _open_connections.append(conn)
    return conn


def _close_thread_connections() -> None:
    with _open_connections_lock:
        for conn in _open_connections:
            if not conn.closed:
                conn.close()
        _open_connections.clear()


def _backfill_market(
    market: dict,
    cutoff_ts: int | None,
    now_ts: int,
    run_id: int,
    limiter: RateLimiter,
    mon: Monitor,
) -> tuple[int, int]:
    """Fetch and land one market's candles together with its ledger row. Returns
    ``(rows, failed)``; a failure is recorded and does not stop the run."""
    conn = _thread_connection()
    ticker = market["ticker"]
    started = time.perf_counter()
    try:
        with mon.timed("kalshi.candles", ticker=ticker) as op:
            start_ts = _parse_kalshi_ts(market["open_time"])
            end_ts = min(_parse_kalshi_ts(market["close_time"]), now_ts)
            settled = (
                _parse_kalshi_ts(market["settlement_ts"]) if market.get("settlement_ts") else None
            )
            historical = bool(cutoff_ts and settled and settled < cutoff_ts)
            candles = (
                fetch_market_candles(
                    ticker, start_ts, end_ts, historical=historical, limiter=limiter
                )
                if start_ts < end_ts
                else []
            )
            df = pd.DataFrame([_flatten_candlestick(ticker, c) for c in candles], columns=None)
            if df.empty:
                df = pd.DataFrame(columns=_CANDLE_BASE_COLUMNS)
            if not df.empty:
                new_columns = set(df.columns) - _known_candle_columns
                if new_columns:
                    with _schema_lock:
                        ensure_table(conn, CANDLE_TABLE, list(df.columns), index_column="ticker")
                        _known_candle_columns.update(df.columns)
            rows = replace_dataframe_scopes(
                conn,
                CANDLE_TABLE,
                df,
                scope_column="ticker",
                scope_values=[ticker],
                schema_drift_policy="ignore",
            )
            record_items(
                conn,
                [
                    _candle_item(
                        ticker,
                        "loaded" if rows else "unavailable",
                        run_id,
                        rows=rows,
                        http_status=200,
                        duration_ms=round((time.perf_counter() - started) * 1000),
                    )
                ],
            )
            conn.commit()
            op.rows = rows
            op.requests = max(1, len(candles) // 4000 + 1)
            return rows, 0
    except Exception as exc:
        conn.rollback()
        logger.error("kalshi candles for %s failed: %s", ticker, exc)
        record_items(conn, [_candle_item(ticker, "failed", run_id, error=str(exc)[:500])])
        conn.commit()
        return 0, 1


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


def backfill_history() -> dict[str, int]:
    """Candlestick history for every landed MLB market, as fast as Kalshi's limit allows.

    Markets settled before ``GET /historical/cutoff`` are read from the ``/historical``
    endpoints (run ``mlb ingest kalshi --mode update`` first so the catalog holds them).
    Runs on ``BACKFILL_WORKERS`` threads behind one shared ``RateLimiter`` (documented
    ceiling 20 requests/s on the Basic tier, paced at 16/s), each with its own HTTP
    session and database connection. One ledger item per market is written in the same
    transaction as its rows, so a rerun skips settled markets already done, retries
    ``failed`` ones and refetches markets that closed less than a day ago. Progress and
    per-market timing go to ``meta.run_progress`` / ``meta.op_span``. Tracked under its
    own source name with no workflow lock so it never blocks the nightly. Raises at the
    end if any market failed, after trying all of them."""
    counts = {CANDLE_TABLE: 0}
    workers = _env_int("MLB_KALSHI_WORKERS", BACKFILL_WORKERS)
    limiter = RateLimiter(float(os.environ.get("MLB_KALSHI_MAX_RPS", BACKFILL_MAX_RPS)))
    with (
        get_connection() as conn,
        track_run(conn, BACKFILL_SOURCE, "backfill", workflow=None) as result,
    ):
        run_id = result["run_id"]
        cutoff = fetch_cutoff().get("market_settled_ts")
        cutoff_ts = _parse_kalshi_ts(cutoff) if cutoff else None
        now_ts = int(time.time())
        ensure_table(conn, CANDLE_TABLE, _CANDLE_BASE_COLUMNS, index_column="ticker")
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'raw' AND table_name = 'kalshi_candle'"
            )
            _known_candle_columns.update(name for (name,) in cur.fetchall())
            cur.execute(
                "SELECT item_key FROM meta.ingestion_item "
                "WHERE source = %s AND dataset = %s AND status IN ('loaded', 'unavailable')",
                (SOURCE, CANDLE_DATASET),
            )
            done = {key for (key,) in cur.fetchall()}
        todo = [
            m
            for m in _candle_markets(conn)
            if not (
                m["ticker"] in done and _parse_kalshi_ts(m["close_time"]) + SETTLE_SECONDS <= now_ts
            )
        ]
        logger.info(
            "kalshi backfill: %d markets to fetch, %d workers, up to %.0f requests/s",
            len(todo),
            workers,
            limiter.rate,
        )
        monitor = Monitor(run_id=run_id)
        total = failed = finished = 0
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [
                    pool.submit(_backfill_market, m, cutoff_ts, now_ts, run_id, limiter, monitor)
                    for m in todo
                ]
                try:
                    for future in as_completed(futures):
                        rows, bad = future.result()
                        total, failed, finished = total + rows, failed + bad, finished + 1
                        monitor.progress(done=finished, planned=len(todo), requests=finished)
                except BaseException:
                    for future in futures:
                        future.cancel()
                    raise
        finally:
            monitor.finish()
            monitor.close()
            _close_thread_connections()
        counts[CANDLE_TABLE] = total
        result["rows"] = total
        if failed:
            raise RuntimeError(
                f"{failed} Kalshi markets failed (recorded as failed in meta.ingestion_item); "
                "rerun the backfill to retry them"
            )
    return counts


def health_check() -> list[Check]:
    return [
        check_table_has_rows(SERIES_TABLE),
        check_table_has_rows(EVENT_TABLE),
        check_table_has_rows(MARKET_TABLE),
        # Sparse-by-design (see check_table_exists) — raw.kalshi_snapshot is
        # only populated while at least one MLB market is currently active,
        # and raw.kalshi_candle only after backfill_history() has been run
        # at least once (an owner-triggered one-off) — 0 rows on a fresh DB
        # isn't unhealthy for either.
        check_table_exists(SNAPSHOT_TABLE),
        # Only exists after the owner-triggered backfill: "not run" is a state,
        # not a missing-table defect.
        check_backfill_state(CANDLE_TABLE),
        # odds-history-capture: a price snapshot every 15 minutes on game days.
        check_snapshot_gaps(SNAPSHOT_TABLE, max_gap_minutes=SNAPSHOT_MAX_GAP_MINUTES),
        check_last_run(SOURCE),
        # mode="update" -- the daily-cron-scheduled mode. Unscoped, a manual
        # backfill_history() run (mode="backfill") would mask a genuinely
        # stale daily update, the same blind spot this check exists to close.
        check_recent_run(SOURCE, FRESHNESS_THRESHOLD_MINUTES, mode="update"),
    ]
