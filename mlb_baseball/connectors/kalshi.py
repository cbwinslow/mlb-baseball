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
per-season API filter to scope a partial reload against.
"""

import pandas as pd
import requests

from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_last_run, check_table_has_rows
from mlb_baseball.ingest import track_run
from mlb_baseball.load import load_dataframe
from mlb_baseball.net import call_with_retry

SOURCE = "kalshi"
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


def _run(mode: str) -> dict[str, int]:
    counts: dict[str, int] = dict.fromkeys(ALL_TABLES, 0)
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

        result["rows"] = sum(counts.values())
    return counts


def bootstrap() -> dict[str, int]:
    return _run("bootstrap")


def update() -> dict[str, int]:
    return _run("update")


def health_check() -> list[Check]:
    return [
        check_table_has_rows(SERIES_TABLE),
        check_table_has_rows(EVENT_TABLE),
        check_table_has_rows(MARKET_TABLE),
        check_last_run(SOURCE),
    ]
