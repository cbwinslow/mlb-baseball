# chadwick_register.py DOX

## Purpose

Own ingestion of the Chadwick Bureau Register, the source-level player/identity
crosswalk used to reconcile IDs across baseball systems.

## Ownership

Source implementation: `chadwick_register.py`.

Owned raw relations:

- `raw.register_people`
- `raw.register_names`
- `raw.register_links`
- `raw.register_countries`

Registry source name: `register`.

Focused integration test: `tests/integration/test_chadwick_register_load.py`.

## Source Contracts

The connector reads Chadwick's public register CSV files from the register
repository's `data/` directory. People are split across the 16 hexadecimal
shards; names, links, and countries are single files.

Raw column names intentionally follow the CSV headers because the raw schema is a
source-faithful mirror and the migration was designed to match those headers.

## Runtime Contracts

- This source is a point-in-time reference snapshot, not an event stream.
- `bootstrap()` and `update()` both perform the same full refresh.
- The four register relations are truncated together before loading so the
  snapshot is internally coherent.
- `raw.register_people` is assembled from all 16 people shards before completion.
- COPY column order comes from each trusted source CSV header.
- A successful rerun replaces the snapshot and does not duplicate rows.
- Run tracking records the combined row count.

Do not turn this into incremental per-row merge logic without evidence that
Chadwick has changed the source's snapshot semantics.

## Downstream Context

This source is high-value identity evidence. Preserve source IDs and aliases even
when another source appears more current. Canonical `core.player` reconciliation
must remain evidence-based and may honestly remain unresolved.

Do not use fuzzy name matching here as authoritative identity truth.

## Failure and Freshness

Network/download or COPY failures must fail visibly; a partial register snapshot
must not be silently treated as complete. Health checks currently require people
rows, successful last run, and recent run state.

## Verification

Run:

```bash
uv run pytest tests/integration/test_chadwick_register_load.py -q
uv run ruff check mlb_baseball/connectors/chadwick_register.py tests/integration/test_chadwick_register_load.py
```

When changing CSV/header behavior, verify all four relations and rerun idempotency.
