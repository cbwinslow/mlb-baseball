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
import time
from datetime import UTC, datetime

import pandas as pd
import psycopg
import requests

from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_last_run, check_table_exists, check_table_has_rows
from mlb_baseball.ingest import track_run
from mlb_baseball.load import append_dataframe, load_dataframe
from mlb_baseball.net import call_with_retry

SOURCE = "polymarket"
BASE_URL = "https://gamma-api.polymarket.com"
CLOB_BASE_URL = "https://clob.polymarket.com"  # prices-history only, confirmed unauthenticated
MLB_SERIES_ID = 3  # confirmed via GET /series?recurrence=daily
MLB_TAG_SLUG = "mlb"  # season-long futures, confirmed via GET /events?tag_slug=mlb
PAGE_SIZE = 100
# Be polite to a public, unauthenticated endpoint across a ~126K-token
# backfill — no documented rate limit was found, but nothing says there
# isn't one either.
BACKFILL_SLEEP_SECONDS = 0.25

EVENT_TABLE = "raw.polymarket_event"
MARKET_TABLE = "raw.polymarket_market"
OUTCOME_TABLE = "raw.polymarket_outcome"
ALL_TABLES = [EVENT_TABLE, MARKET_TABLE, OUTCOME_TABLE]
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
            counts[table] = load_dataframe(conn, table, df)

        # Forward snapshot (ADR-049): append-only, never replaced — every
        # run's open-market prices stay meaningful as a point-in-time
        # observation, not just the latest one. Always calls
        # append_dataframe, even with 0 rows on a day with no open markets,
        # so raw.polymarket_snapshot's own existence doesn't depend on the
        # coincidence of an open market at run time — same fix
        # mlb_api.capture_live() already needed for raw.mlb_live_game.
        captured_at = datetime.now(UTC).isoformat()
        snapshot_df = pd.DataFrame(_snapshot_rows(events, captured_at), columns=SNAPSHOT_COLUMNS)
        counts[SNAPSHOT_TABLE] = append_dataframe(conn, SNAPSHOT_TABLE, snapshot_df)

        conn.commit()
        result["rows"] = sum(counts.values())
    return counts


def bootstrap() -> dict[str, int]:
    return _run("bootstrap")


def update() -> dict[str, int]:
    return _run("update")


def _clob_get(url: str, params: dict) -> dict:
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_price_history(token_id: str) -> list[dict]:
    """Calls the CLOB API's /prices-history endpoint for one outcome token.
    Confirmed live (not from docs alone): `market=<clob_token_id>&
    interval=max` returns `{"history": [{"t": <unix_seconds>, "p": <price>},
    ...]}` — a real per-token timeseries (926 points confirmed on a real
    settled MLB moneyline token). A token with no matching/tradeable market
    (bad id, or one that genuinely never traded) returns `{"history": []}`
    with a normal HTTP 200, not a 404 — confirmed directly — so an empty
    result is a valid, expected outcome here, not an error to retry."""
    payload = call_with_retry(
        _clob_get, f"{CLOB_BASE_URL}/prices-history", {"market": token_id, "interval": "max"}
    )
    return payload.get("history", [])


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
            SELECT o.clob_token_id, m.id AS market_id, e.id AS event_id
            FROM raw.polymarket_event e
            JOIN raw.polymarket_market m ON m.event_id = e.id
            JOIN raw.polymarket_outcome o ON o.market_id = m.id
            WHERE e.sport IS NOT NULL
              AND o.clob_token_id IS NOT NULL AND o.clob_token_id <> ''
            ORDER BY m.id
            """
        )
        return [
            {"clob_token_id": token, "_market": market_id, "_event": event_id}
            for token, market_id, event_id in cur.fetchall()
        ]


def backfill_history() -> dict[str, int]:
    """One-off historical backfill of per-token price timeseries via the
    CLOB API — see ADR-049, reversing ADR-026's original exclusion.
    Deliberately separate from bootstrap()/update() (which only ever land
    the *current* outcomePrices snapshot): this is an owner-triggered `mlb
    ingest polymarket --mode backfill`, expected to take hours across
    ~126K tokens, not something a 5-minute/daily cron should ever run.

    Commits once per market, not once per token — an interrupted run loses
    at most one market's worth of tokens (usually 2, sometimes more for a
    multi-outcome prop), not the whole backfill. Each token's own load is
    independently scoped-replace (scope_column=clob_token_id), so a re-run
    after an interruption is safe: already-landed tokens are just replaced
    with the same data, not duplicated.
    """
    counts = {PRICE_TABLE: 0}
    with get_connection() as conn, track_run(conn, SOURCE, "backfill") as result:
        tokens = _daily_game_tokens(conn)
        by_market: dict[str, list[dict]] = {}
        for row in tokens:
            by_market.setdefault(row["_market"], []).append(row)

        total = 0
        for _market_id, rows in by_market.items():
            for row in rows:
                history = fetch_price_history(row["clob_token_id"])
                if not history:
                    continue
                df = pd.DataFrame(
                    [
                        {
                            "clob_token_id": row["clob_token_id"],
                            "_market": row["_market"],
                            "_event": row["_event"],
                            "ts": point["t"],
                            "price": point["p"],
                        }
                        for point in history
                    ]
                )
                total += load_dataframe(
                    conn,
                    PRICE_TABLE,
                    df,
                    scope_column="clob_token_id",
                    scope_value=row["clob_token_id"],
                )
                time.sleep(BACKFILL_SLEEP_SECONDS)
            conn.commit()

        counts[PRICE_TABLE] = total
        result["rows"] = total
    return counts


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
        check_table_exists(PRICE_TABLE),
        check_last_run(SOURCE),
    ]
