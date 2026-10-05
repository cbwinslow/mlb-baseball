# `kalshi.py` DOX

## Purpose

Own public read-only Kalshi MLB market ingestion, including MLB series/event/contract state, forward price snapshots, and historical one-minute candlestick backfill for the daily game-moneyline series. This source has shallow historical depth but strong current/future point-in-time value.

## Ownership

Implementation: `kalshi.py`.

Primary raw outputs:

- `raw.kalshi_series`
- `raw.kalshi_event`
- `raw.kalshi_market`
- `raw.kalshi_snapshot`
- `raw.kalshi_candle`

Public connector capabilities:

- `bootstrap()`
- `update()`
- `snapshot()` — price-only capture of open markets (called by `mlb odds-capture` every 15 minutes; never touches the catalog; recorded as run mode `snapshot` under source `kalshi_snapshot`, without the workflow lock)
- `backfill_history()`
- `health_check()`

## Source Contract

- Public read-only API: `api.elections.kalshi.com/trade-api/v2`.
- Current connector uses unauthenticated market-data reads; authenticated trading/portfolio requests are a different capability and are not part of this implementation.
- Baseball series are discovered from Sports/Baseball and explicitly filtered to true MLB scope.
- `EXCLUDED_SERIES_TICKERS` is evidence-driven: KBO, NPB, Mexican league, MiLB, NCAA, WBC, charity/deprecated/non-MLB products are excluded after checking their actual series titles.
- Everything else in MLB scope remains eligible, including game lines, spreads/totals, season totals, player props, awards, futures, draft, All-Star/Home Run Derby, and other MLB products.
- Daily game moneyline series `KXMLBGAME` currently has genuinely shallow history beginning in 2026; do not invent deeper Kalshi sports-market history.
- Repository rights/profile metadata remains authoritative for permitted use/redistribution; unauthenticated readability is not a redistribution license.

## Market Data Contract

- A Kalshi `market` is already an atomic yes/no contract with bid/ask/last-price/volume/open-interest fields; unlike Polymarket, there is no separate outcome-array explosion step.
- Series ticker, event ticker, and market ticker are source identities, not canonical MLB identities.
- Current/settled contract price is not automatically the correct historical pregame probability. Timestamped snapshot/candle observations must be used for PIT research.

## Runtime Contracts

### Pagination and endpoint ceilings

- `/markets` and `/events` have different empirically verified safe page sizes. Preserve the separate constants rather than assuming one endpoint's limit applies to all.
- Market pulls use `mve_filter=exclude` according to current source behavior.
- Paginated series failures are isolated/logged so one problematic series does not discard all other MLB series data.

### MLB filtering

- Do not replace the explicit exclusions with ticker-name guessing alone. The Baseball tag contains materially non-MLB products.
- When Kalshi adds/renames a series, inspect its actual title/product before changing inclusion/exclusion policy.

### Bootstrap/update

- `bootstrap()` and `update()` currently perform the same full reload for catalog tables because one paginated pull can return open/closed/settled states and there is no useful per-season load boundary.
- Series/event/market catalog tables replace only the keys returned (`upsert_dataframe`); rows the source stops returning are kept and `_loaded_at` is their last-seen time (ADR-294). Never switch back to whole-table replace.
- Each run appends current active-market observations to `raw.kalshi_snapshot` using the already-fetched market payload.
- Snapshot identity is `(ticker, captured_at)` and is append-only because every observation time is meaningful.
- Snapshot schema must exist even if no markets are active at a particular run.

### Historical catalog and candlestick backfill

- Kalshi splits data at `GET /historical/cutoff` (checked live 2026-10-05: 2026-08-06): markets and candlesticks settled before it are only on the `/historical` endpoints; the live `/markets` listing no longer returns them. `update()` therefore also pages `/historical/markets` per series and merges (live wins on a ticker). Before this, `raw.kalshi_market` held only about 1,700 game markets from July 2026 while Kalshi had 7,868 from 2025-04-16 (`KXMLBGAME`).
- `backfill_history()` is separate from normal bootstrap/update. Scope is every landed MLB market (all non-excluded baseball series), game-level series first (smaller series first), newest market first.
- Each market's candles come from `/historical/markets/{ticker}/candlesticks` if it settled before the cutoff, else `/series/{series}/markets/{ticker}/candlesticks`; a 404 falls back to the other. 1-minute candles, windows of at most 4,000 minutes (the endpoint rejects more than 5,000 candles).
- Signing: with `KALSHI_API_KEY` (key id) and `KALSHI_PRIVATE_KEY_PATH` (the PEM Kalshi gives when a free key is created) every request is RSA-PSS signed (`signed_headers`). Unsigned public requests work but returned 429s from about 5 requests/s (measured 2026-10-05).
- Speed: signed Basic tier 200 read tokens/s at 10 per request = 20 requests/s, paced at 16/s (5/s unsigned) by a shared `net.RateLimiter` (halves on 429); 8 worker threads, each with its own HTTP session and database connection. Override with `MLB_KALSHI_WORKERS` / `MLB_KALSHI_MAX_RPS`; raise only with a new measurement.
- One ledger item per market (`meta.ingestion_item`, dataset `candles`, key = ticker; `loaded`, `unavailable` for no candles, `failed`) is written in the same transaction as the rows. A rerun skips settled markets already done, retries failed ones, refetches markets closed less than a day ago, and raises at the end if any failed.
- Tracked under its own source name `kalshi_backfill` with no workflow lock, so it never blocks the nightly or conform/predict.
- Empty/no-trade price subobjects are valid source observations; flatten them with missing values rather than fabricating prices. Quote columns (`yes_bid`, `yes_ask`) are kept for minutes with no trade.
- Not yet covered: per-market trades (`/historical/trades`, `/markets/trades`), tracked in `openspec/changes/odds-bulk-history` task 4.3.

## Point-in-Time Contract

- `captured_at` on snapshots and candle period timestamps are the observation-time evidence used for historical market features.
- Pregame research must select observations valid before the game/forecast cutoff.
- Bid, ask, and last price represent different market concepts; do not silently collapse them into one "probability" without an explicit transformation contract.
- Resolved/settled outcome state must never leak into a pregame model feature.
- If no valid pre-cutoff observation exists, preserve missingness.

## Dependencies

- `requests`
- pandas / psycopg
- `call_with_retry`
- `load_dataframe` / `append_dataframe`
- `track_run`
- DB and health helpers

## Downstream Consumers

- `conform.py` currently resolves Kalshi MLB game markets into canonical game/team identity and point-in-time market context.
- Future normalized market contracts should preserve contract identity and observation history rather than reducing Kalshi to a mutable latest price.
- Value/model comparisons must account for the exact observed price field/time and keep market/model/fair-price concepts separate.

## Known Quirks / Decisions

- Baseball-tagged series include many non-MLB products; explicit exclusions are required.
- Read-only public endpoints do not require the heavy authenticated-request signing flow used for trading.
- Kalshi's MLB game market history is new/shallow relative to Polymarket.
- One-minute candlestick requests must be chunked to remain below endpoint response limits.
- Forward snapshots and historical candlesticks are complementary: snapshots keep current history going; backfill fills available past history.

## Work Guidance

- Verify new endpoint/page-limit/series claims with bounded real-source checks before encoding them as durable rules.
- Do not add trading/authenticated account behavior to this connector without separate security/product design.
- Preserve source bid/ask/last distinctions and timestamps.
- New included market families must still be demonstrably MLB-related and permitted under the active source profile.
- Avoid string-only MLB game identity when event/market source IDs plus downstream canonical reconciliation can do better.

## Verification

For changes, verify:

- baseball-series filtering and exclusions;
- events/markets pagination at endpoint-specific page sizes;
- catalog full-reload idempotency;
- active snapshot filtering/append identity/zero-active behavior;
- candlestick chunk boundaries and 1-minute granularity;
- flattening of empty/no-trade nested candle fields;
- retry/rate-limit behavior with deterministic HTTP fixtures;
- downstream conformance/PIT tests for game matching and pregame observation selection;
- health checks for catalog/snapshot/candle data.

Use live Kalshi calls only for bounded source verification, then preserve deterministic fixtures for CI.

## Child DOX Index

No child DOX files. This is a leaf connector contract.
