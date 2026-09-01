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
- Series/event/market catalog tables use replace semantics.
- Each run appends current active-market observations to `raw.kalshi_snapshot` using the already-fetched market payload.
- Snapshot identity is `(ticker, captured_at)` and is append-only because every observation time is meaningful.
- Snapshot schema must exist even if no markets are active at a particular run.

### Historical candlestick backfill

- `backfill_history()` is separate from normal bootstrap/update.
- Current scope is `KXMLBGAME` daily MLB game moneylines, deliberately narrower than every MLB product.
- The candlestick endpoint supports fine 1-minute data but rejects overly wide windows with a confirmed `max candlesticks: 5000` error.
- `fetch_candlesticks()` therefore chunks time ranges rather than silently reducing granularity.
- Empty/no-trade price subobjects are valid source observations; flatten them with missing values rather than fabricating prices.
- Backfill should remain resumable/idempotent at the market/time-series scope and should not become a routine high-frequency update side effect.
- `BACKFILL_SLEEP_SECONDS` exists because this public source has produced real rate-limit pressure. Do not remove politeness/retry controls without evidence.

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