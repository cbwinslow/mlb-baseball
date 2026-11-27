# Staged ingestion layer DOX

## Purpose

The standard path for new and migrated sources: **download -> typed Arrow/polars batch -> `dlt` -> PostgreSQL**, each stage replaceable. Spec: `openspec/changes/dlt-ingestion-layer/` (design D1-D10, `results.md` for measured speed). Sources move over one at a time with a parity test; the old connector path stays runnable until the owner approves retiring it.

## Ownership

- `types.py` — declared column types per table (reuses `market_store.MarketTable`/`Column`, no second registry) and `cast()`: empty string -> NULL (never zero), non-throwing cast, bad rows returned as source text with a reason.
- `land.py` — `land()`: casts, runs the frame through `dlt` in a throwaway folder, then ONE transaction: landing policy (`APPEND`, `UPSERT`, `REPLACE_SCOPE`, `TRUNCATE`), rejects, and one `meta.ingestion_item` row per item with rows actually inserted. Nothing is written to PostgreSQL unless `dlt` finished.
- `state.py` — working-folder location (`$MLB_HOME/dlt`, default `~/.mlb/dlt`); losing it loses nothing.

## Rules

- Pass typed Arrow/polars, never Python dicts: `dlt` is ~10x slower on dicts (`results.md`).
- Batch many ledger items per `land()` call; each call costs ~0.15 s fixed.
- No `_dlt_*` table or column may reach `raw`/`core`/`gold`/`meta`; `dlt` never connects to PostgreSQL here.
- Types are declared per table, source by source. `load.py.dox.md` still governs the old all-text raw landing; do not retype a table without its parity plan.
- `retrieved_at` on an item is download time, not load time. Missing measurement is NULL.
- A new source field is added as `text` and logged; it is never silently dropped.

## Verification

`tests/unit/test_ingest_layer_types.py`, `tests/integration/test_ingest_layer_land.py` (policies, atomicity, zero-row item, leftover failed load, empty vs NULL, no `_dlt_*` objects), `tests/integration/test_ingest_layer_bench.py` (speed against the current Polymarket loader; run with `-s`).

## Child DOX Index

No child DOX.
