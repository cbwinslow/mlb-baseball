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
  candlesticks endpoint (`GET /series/{series_ticker}/markets/{ticker}/
  candlesticks`), confirmed working unauthenticated directly, same as every
  other endpoint here. Scoped to `KXMLBGAME` (daily game moneylines) only,
  per the owner's direction — Kalshi's own sports-contract history is
  shallow (KXMLBGAME starts 2026-05-22), so this is a much smaller job than
  Polymarket's. Confirmed the endpoint rejects a request spanning too many
  candles at a given granularity with a plain 400 ("max candlesticks:
  5000") — `fetch_candlesticks()` chunks the requested time range so no
  single call can hit that ceiling, rather than picking a coarser
  granularity and losing detail.
- Forward snapshots (above) keep the series current going forward.
"""

import time
from datetime import UTC, datetime

import pandas as pd
import psycopg
import requests

from mlb_baseball.db import get_connection
from mlb_baseball.health import (
    DAILY_FRESHNESS_THRESHOLD_MINUTES,
    Check,
    check_last_run,
    check_recent_run,
    check_table_exists,
    check_table_has_rows,
)
from mlb_baseball.ingest import track_run
from mlb_baseball.load import append_dataframe, load_dataframe
from mlb_baseball.net import call_with_retry

SOURCE = "kalshi"
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

CANDLE_SERIES_TICKER = "KXMLBGAME"  # daily MLB game moneylines only, per ADR-049
# Maximum available granularity (1-minute candles) — confirmed the
# candlesticks endpoint's own ceiling is 5000 candles per request, so a
# single-market request window is kept comfortably under that regardless of
# how long a given market stayed open.
CANDLE_PERIOD_INTERVAL_MINUTES = 1
CANDLE_CHUNK_MINUTES = 4000
# Be polite to a public, unauthenticated endpoint across a multi-market
# backfill — no documented rate limit was found, but the connector already
# hit real 429s once during a production bootstrap (see module docstring
# above / ADR-026's rationale for retry-with-backoff), so a small pause
# between markets costs little and avoids provoking one here too.
BACKFILL_SLEEP_SECONDS = 0.25

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


def fetch_markets(series_ticker: str) -> list[dict]:
    return _paginate(
        "/markets", series_ticker, "markets", MARKETS_PAGE_SIZE, {"mve_filter": "exclude"}
    )


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


def _run(mode: str) -> dict[str, int]:
    counts: dict[str, int] = dict.fromkeys(ALL_TABLES, 0)
    counts[SNAPSHOT_TABLE] = 0
    with get_connection() as conn, track_run(conn, SOURCE, mode) as result:
        series = fetch_series()
        if series:
            counts[SERIES_TABLE] = load_dataframe(conn, SERIES_TABLE, pd.DataFrame(series))
            conn.commit()

        all_events: list[dict] = []
        all_markets: list[dict] = []
        for s in series:
            ticker = s["ticker"]
            try:
                all_events.extend(fetch_events(ticker))
                all_markets.extend(fetch_markets(ticker))
            except Exception as exc:
                print(f"kalshi: {ticker} failed ({exc}); skipping, continuing bootstrap")

        if all_events:
            counts[EVENT_TABLE] = load_dataframe(conn, EVENT_TABLE, pd.DataFrame(all_events))
            conn.commit()
        if all_markets:
            counts[MARKET_TABLE] = load_dataframe(conn, MARKET_TABLE, pd.DataFrame(all_markets))
            conn.commit()

        # Forward snapshot (ADR-049): append-only, never replaced — every
        # run's active-market prices stay meaningful as a point-in-time
        # observation, not just the latest one. Always calls
        # append_dataframe, even with 0 rows on a run with no active
        # markets, so raw.kalshi_snapshot's own existence doesn't depend on
        # the coincidence of an active market at run time — same fix
        # mlb_api.capture_live() already needed for raw.mlb_live_game.
        captured_at = datetime.now(UTC).isoformat()
        snapshot_df = pd.DataFrame(
            _snapshot_rows(all_markets, captured_at), columns=SNAPSHOT_COLUMNS
        )
        counts[SNAPSHOT_TABLE] = append_dataframe(
            conn,
            SNAPSHOT_TABLE,
            snapshot_df,
            identity_columns=("ticker", "captured_at"),
        )
        conn.commit()

        result["rows"] = sum(counts.values())
    return counts


def bootstrap() -> dict[str, int]:
    return _run("bootstrap")


def update() -> dict[str, int]:
    return _run("update")


def fetch_candlesticks(
    series_ticker: str,
    market_ticker: str,
    start_ts: int,
    end_ts: int,
    period_interval: int = CANDLE_PERIOD_INTERVAL_MINUTES,
) -> list[dict]:
    """Calls GET /series/{series_ticker}/markets/{ticker}/candlesticks,
    confirmed working unauthenticated directly against a real, settled
    KXMLBGAME market. Chunks [start_ts, end_ts] into windows of at most
    CANDLE_CHUNK_MINUTES so no single request can hit the endpoint's
    confirmed real ceiling (a too-wide range 400s with "max candlesticks:
    5000", found by calling it directly, not documented anywhere)."""
    candles: list[dict] = []
    chunk_seconds = CANDLE_CHUNK_MINUTES * 60
    chunk_start = start_ts
    while chunk_start < end_ts:
        chunk_end = min(chunk_start + chunk_seconds, end_ts)
        payload = call_with_retry(
            _get,
            f"{BASE_URL}/series/{series_ticker}/markets/{market_ticker}/candlesticks",
            {
                "start_ts": chunk_start,
                "end_ts": chunk_end,
                "period_interval": period_interval,
            },
        )
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


def _kxmlbgame_markets(conn: psycopg.Connection) -> list[dict]:
    """Every already-landed KXMLBGAME market with a real open_time/
    close_time — the basis for scoping the candlestick backfill's time
    window per market. Confirmed empirically that KXMLBGAME's own market
    objects carry ISO8601 open_time/close_time fields directly (see module
    docstring)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT ticker, open_time, close_time FROM raw.kalshi_market "
            "WHERE ticker LIKE 'KXMLBGAME-%' AND open_time IS NOT NULL "
            "AND close_time IS NOT NULL"
        )
        return [{"ticker": t, "open_time": o, "close_time": c} for t, o, c in cur.fetchall()]


def _parse_kalshi_ts(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def backfill_history() -> dict[str, int]:
    """One-off historical candlestick backfill for KXMLBGAME (MLB daily-game
    moneyline) markets — see ADR-049. Not run by bootstrap()/update() — an
    owner-triggered `mlb ingest kalshi --mode backfill`. Kalshi's own
    sports-contract history is shallow (KXMLBGAME starts 2026-05-22), so
    this is a much smaller job than Polymarket's price-history backfill.

    Commits once per market (same resumability reasoning as
    polymarket.backfill_history) — scoped-replace by ticker, so a re-run
    after an interruption replaces only the tickers it actually reprocesses,
    never duplicates.
    """
    counts = {CANDLE_TABLE: 0}
    with get_connection() as conn, track_run(conn, SOURCE, "backfill") as result:
        markets = _kxmlbgame_markets(conn)
        now_ts = int(time.time())
        total = 0
        for market in markets:
            start_ts = _parse_kalshi_ts(market["open_time"])
            end_ts = min(_parse_kalshi_ts(market["close_time"]), now_ts)
            if start_ts >= end_ts:
                continue
            candles = fetch_candlesticks(CANDLE_SERIES_TICKER, market["ticker"], start_ts, end_ts)
            if not candles:
                continue
            df = pd.DataFrame([_flatten_candlestick(market["ticker"], c) for c in candles])
            total += load_dataframe(
                conn, CANDLE_TABLE, df, scope_column="ticker", scope_value=market["ticker"]
            )
            conn.commit()
            time.sleep(BACKFILL_SLEEP_SECONDS)

        counts[CANDLE_TABLE] = total
        result["rows"] = total
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
        check_table_exists(CANDLE_TABLE),
        check_last_run(SOURCE),
        # mode="update" -- the daily-cron-scheduled mode. Unscoped, a manual
        # backfill_history() run (mode="backfill") would mask a genuinely
        # stale daily update, the same blind spot this check exists to close.
        check_recent_run(SOURCE, FRESHNESS_THRESHOLD_MINUTES, mode="update"),
    ]
