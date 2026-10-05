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
- `snapshot()`
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
- Catalog tables replace only the keys returned (`upsert_dataframe`; event `id`, market `id`, outcome `market_id`); rows the source stops returning are kept and `_loaded_at` is their last-seen time (ADR-294). Never switch back to whole-table replace.
- `snapshot()` is the price-only capture (open events only, appends to `raw.polymarket_snapshot`) run by `mlb odds-capture` every 15 minutes; recorded as run mode `snapshot` under source `polymarket_snapshot`, without the workflow lock.
- Every run also appends **current prices for open markets** into `raw.polymarket_snapshot` using the already-fetched event payload—no extra catalog request.
- Snapshot identity is `(market_id, outcome, captured_at)` and observations are append-only because each timestamp remains meaningful.
- The snapshot table should exist even on a run with zero open markets; do not make schema existence depend on current-market coincidence.

### Historical price backfill

- `backfill_history()` is deliberately separate from routine bootstrap/update.
- It uses `POST clob.polymarket.com/batch-prices-history` (20 tokens per request) over fixed 14-day windows, newest window first. `interval=max` returns an empty list for a settled market and the API rejects a 30-day window (checked live 2026-10-05); do not reintroduce either.
- Speed is measured, not guessed: a 20-token 14-day request takes about 0.3 s, throughput stops rising past roughly 8-16 concurrent requests (32 concurrent heavy requests timed out), the documented ceiling is 1,000 requests / 10 s with no key. Settings: `BACKFILL_WORKERS` (12), `BACKFILL_MAX_RPS` (90, shared `net.RateLimiter`, halves on a 429), env overrides `MLB_POLYMARKET_WORKERS` / `MLB_POLYMARKET_MAX_RPS`. Change them only with a new measurement.
- Each worker owns an HTTP session and a database connection. One transaction per request writes the window's rows (`load.replace_dataframe_range`: replaces only that token-and-window) and the ledger rows (`meta.ingestion_item`, dataset `price_history`, key `<token>:<window start>`; `loaded`, or `unavailable` for an empty window; `failed` with the error).
- A rerun skips settled windows already in the ledger, retries `failed` ones, and refetches windows that ended less than a day ago. The run raises at the end if any window failed.
- Markets with no start date are recorded `unavailable` (no window can be requested).
- Progress and per-request timing go to `meta.run_progress` / `meta.op_span` (`polymarket.batch`); check `meta.run_health` for rate and ETA.
- Scale (2026-10-05): about 435,000 tokens over 217,000 markets.

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
