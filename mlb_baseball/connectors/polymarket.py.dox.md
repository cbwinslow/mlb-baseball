# `polymarket.py` DOX

## Purpose

Own public read-only Polymarket MLB market ingestion, including catalog/current market state, forward price snapshots, and an explicit historical price-timeseries backfill path. This source is especially important for future market comparison/value research, so event identity and **observation-time semantics** are part of correctness.

## Ownership

Implementation: `polymarket.py`.

Primary raw outputs:

- `raw.polymarket_event`
- `raw.polymarket_market`
- `raw.polymarket_outcome`
- `raw.polymarket_snapshot`
- `raw.polymarket_price`

Public connector capabilities:

- `bootstrap()`
- `update()`
- `backfill_history()`
- `health_check()`

## Source Contract

- Catalog/current-state API: public Gamma API at `gamma-api.polymarket.com`.
- Historical token price API: public CLOB endpoint at `clob.polymarket.com/prices-history`.
- Current implementation performs unauthenticated read access only. Do not infer permission for trading/account actions from this connector.
- Daily MLB game events are discovered through MLB daily series id `3`.
- Broader MLB-tagged events are discovered through `tag_slug=mlb`; this includes overlapping daily games plus futures/postseason/draft/All-Star/other MLB-tagged products.
- The two event queries overlap heavily; canonical raw load de-duplicates by Polymarket event id before loading.
- Daily-game catalog history is materially deeper than Kalshi and currently reaches back to 2021 based on direct endpoint pagination evidence in the source.
- Canonical redistribution/profile rights remain owned by repository source-rights metadata/docs; public API accessibility does not by itself define redistribution rights.

## Market / Outcome Data Contract

- One Polymarket market can expose parallel JSON-encoded `outcomes`, `outcomePrices`, and `clobTokenIds` arrays.
- The connector explodes those arrays into one row per outcome in `raw.polymarket_outcome`; do not collapse them back into an opaque blob if downstream identity/price history requires token-level rows.
- Event, market, outcome, and CLOB token ids are source identifiers. They do not become canonical MLB game/team identities until conformance resolves them.
- Current/settled `outcomePrices` are source state, **not automatically a pregame probability**. Historical research must select a timestamped observation valid before the game cutoff.

## Runtime Contracts

### Pagination

- Deep event history uses `/events/keyset`, not offset pagination.
- Plain offset pagination was empirically found to fail beyond the endpoint's shallow offset ceiling; reverting to offset pagination can silently truncate MLB history.
- Continue until `next_cursor` is absent/empty.

### Bootstrap/update

- `bootstrap()` and `update()` currently perform the same full catalog reload because the API does not provide a reliable natural per-season event filter and total catalog volume is manageable.
- Full catalog tables use replace semantics.
- Every run also appends **current prices for open markets** into `raw.polymarket_snapshot` using the already-fetched event payload—no extra catalog request.
- Snapshot identity is `(market_id, outcome, captured_at)` and observations are append-only because each timestamp remains meaningful.
- The snapshot table should exist even on a run with zero open markets; do not make schema existence depend on current-market coincidence.

### Historical price backfill

- `backfill_history()` is deliberately separate from routine bootstrap/update.
- It calls CLOB `/prices-history` per outcome token with `interval=max`.
- Current intentional scope is daily-game-event tokens, not every futures/draft/postseason tagged token.
- A token returning an empty history with HTTP 200 is a valid no-trade/no-history result, not automatically a retryable error.
- Historical loads are scoped by `clob_token_id`, making reruns idempotent rather than duplicative.
- Commit/resume behavior is intentionally finer than the entire backfill so an interruption does not discard hours of already-landed work.
- `BACKFILL_SLEEP_SECONDS` is deliberate public-endpoint politeness. Do not remove it or raise concurrency without measured rate-limit/reliability evidence.

## Point-in-Time Contract

This is the most important downstream rule for this source:

- Price state must carry a real observation timestamp (`captured_at` or CLOB history timestamp).
- A historical pregame market probability must resolve from an observation strictly before the game's actual start/cutoff according to the owning research contract.
- If there is no qualifying observation, preserve `NULL`/missing rather than substituting current, closing, or settled price.
- Do not use market resolution/outcome fields as a model feature before the outcome was knowable.

`conform.py` / future market-normalization code owns the canonical MLB game/team matching and PIT selection; this connector owns source-faithful observations.

## Dependencies

- `requests`
- pandas / psycopg
- `call_with_retry`
- `load_dataframe` / `append_dataframe`
- `track_run`
- DB and health helpers

## Downstream Consumers

- `conform.py` / `core.market` currently resolves per-game market identity and a valid pregame snapshot.
- Future `core.market` + `market_observation` normalization should preserve source contract identity and observation history rather than flattening Polymarket into one mutable probability.
- Forecast/value research may compare model probabilities to permitted timestamped market probabilities, but source probability and model probability remain separate artifacts.

## Known Quirks / Decisions

- Daily series and MLB tag queries overlap; de-duplication by event id is required.
- `tag_slug=mlb` is broader than season futures and cannot be treated as game-only data.
- Intraday history was intentionally added after earlier project scope excluded it; do not remove price history merely because current snapshots are simpler.
- Historical price backfill scale is large enough to be an explicit operator action, not a routine cron/update side effect.

## Work Guidance

- Any endpoint/pagination/scope change should be checked against real API behavior with a bounded probe before becoming durable documentation.
- Preserve append-only observation history.
- Do not add authenticated trading/account behavior to this read-only connector casually; that is a separate security/product capability.
- When adding more market types/backfill scope, document source volume, API cost, rights/profile implications, identity mapping, and PIT usage first.
- Avoid treating Polymarket ticker/title string matching as canonical identity when stable source IDs + downstream reconciliation are available.

## Verification

For behavior changes, verify:

- keyset pagination and de-duplication;
- event/market/outcome flattening and parallel-array edge cases;
- full reload idempotency;
- open-market snapshot append identity and zero-open-market behavior;
- historical price empty-history behavior and token-scoped rerun idempotency;
- retry/rate-limit/error paths with deterministic HTTP fixtures;
- downstream conformance/PIT tests for game matching and pregame snapshot selection;
- health checks for catalog/snapshot/price relations as applicable.

Use live API calls only for bounded parity/coverage confirmation, then capture deterministic evidence for CI.

## Child DOX Index

No child DOX files. This is a leaf connector contract.