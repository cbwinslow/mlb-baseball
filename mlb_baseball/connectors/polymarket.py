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

Deliberately NOT built: intraday price history via the CLOB API's
`/prices-history` endpoint (confirmed working — real per-token timeseries
data exists). Landing that would mean one CLOB call per outcome per market
across thousands of historical events, an order of magnitude more calls
for data this project doesn't have an immediate use for; `outcomePrices`
already gives the current/final market-implied probability for every
market, open or closed (a closed market's price reflects its resolved
outcome). Same reasoning as excluding pybaseball's `get_splits()` in
ADR-024 — real, working, but no practical bulk form worth the cost right
now. Revisit if a future modeling need specifically requires intraday
price movement, not just settled/current probabilities.

bootstrap() and update() are the same full reload (like
chadwick_register.py/retrosheet_reference.py) — total volume (5,926 events,
64K market rows) is comparable to other full-reload/full-table sources
already in this project (e.g. raw.retrosheet_teamstats' 501K rows), and
there's no natural per-season API filter to scope a partial reload against
anyway (confirmed: the events endpoint's start_date_min/max params, which
work on /markets, return nothing when applied to /events).
"""

import json

import pandas as pd
import requests

from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_last_run, check_table_has_rows
from mlb_baseball.ingest import track_run
from mlb_baseball.load import load_dataframe
from mlb_baseball.net import call_with_retry

SOURCE = "polymarket"
BASE_URL = "https://gamma-api.polymarket.com"
MLB_SERIES_ID = 3  # confirmed via GET /series?recurrence=daily
MLB_TAG_SLUG = "mlb"  # season-long futures, confirmed via GET /events?tag_slug=mlb
PAGE_SIZE = 100

EVENT_TABLE = "raw.polymarket_event"
MARKET_TABLE = "raw.polymarket_market"
OUTCOME_TABLE = "raw.polymarket_outcome"
ALL_TABLES = [EVENT_TABLE, MARKET_TABLE, OUTCOME_TABLE]

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


def _run(mode: str) -> dict[str, int]:
    counts: dict[str, int] = dict.fromkeys(ALL_TABLES, 0)
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
        conn.commit()
        result["rows"] = sum(counts.values())
    return counts


def bootstrap() -> dict[str, int]:
    return _run("bootstrap")


def update() -> dict[str, int]:
    return _run("update")


def health_check() -> list[Check]:
    return [
        check_table_has_rows(EVENT_TABLE),
        check_table_has_rows(MARKET_TABLE),
        check_table_has_rows(OUTCOME_TABLE),
        check_last_run(SOURCE),
    ]
