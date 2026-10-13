# Design

## Context

Evidence is tagged V (checked in this session) or A (assumed, to be tested).

- 18 connectors are registered in `registry.py`; sizes range from 87 lines (`retrosheet_schedule.py`) to 3,606 (`mlb_api.py`). Each re-implements fetch, paging/windowing, retry, drift handling and loading on top of shared helpers: `net.py` (`get_with_retry`, `call_with_retry`, `RateLimiter`), `manifest.py` (kept downloads with sha256), `load.py` (scoped replace, append, upsert), `market_store.py` (typed append-only landing, built in `stabilize-and-market-store`), `ingest.py` (`track_run`, `record_items` into `meta.ingestion_item`), `shard.py` (process sharding), `source_profiles.py` (rights) [V].
- ADR-300 rejected `dlt` on 2026-10-07 because it would be "a second loader with its own state and schema rules" [V]. That objection is answered here by keeping our loader and ledger as the destination (D3), not by ignoring it.
- `dlt` facts checked in its documentation today [V]: write dispositions `append`/`replace`/`merge` (Postgres merge strategies `delete-insert`, `upsert`, `scd2`, `insert-only`); schema contracts (`freeze`/`evolve`/`discard`); load tracking in `_dlt_loads`; the default naming convention is `snake_case` but `direct` keeps source names; a custom destination function receives batches, uses no nested sub-tables by default, can skip `_dlt_*` columns/tables, and with `batch_size=0` receives one call per load job with the file path; Postgres supports DDL transactions. Not yet verified here: throughput at our request rates and whether rows plus a ledger row can commit together from a custom destination (D3 gate).
- Constraints from the repo: raw is source-faithful (`load.py.dox.md`), ADR-299 keeps Chadwick for Retrosheet event parsing, ADR-288 keeps the FanGraphs user-agent exemption, ADR-301 `schema-watch` stays, one change per session (project doctrine).

## Goals / Non-Goals

**Goals:**
- Download, load and check are separate parts; replacing the fetch tool, the storage engine or one source does not touch the others.
- `dlt` does fetching, paging, retries, incremental cursors and schema contracts for sources that need them.
- Move all 18 connectors over, one at a time, each proven by a parity check and reversible.

**Non-Goals:**
- No new data source, no paid service, no `core`/`gold` change, no SQLMesh change.
- No replacement of the Chadwick tools; they stay a parse step between download and load.
- Not a big-bang rewrite: a connector that has not migrated keeps working unchanged.

## Decisions

**D1. Three stage interfaces as small Protocols, no framework.**
`Downloader` (yields artifacts: path, URL, retrieved-at, size, sha256), `Loader` (artifact or batch to landed rows plus count), `Check` (the existing `health.Check`). A source module wires one of each. Lives in `mlb_baseball/ingest_layer/`. Why: the interfaces are the decoupling; anything bigger (plugin discovery, base classes) is speculative (`mlb_baseball/AGENTS.md`). Alternative: keep per-connector modules and only share helpers (status quo, rejected: this is what produced 3,606-line modules).

**D2. `dlt` is the extract and normalize engine.**
Per source, a `dlt` resource/source in `ingest_layer/sources/<source>.py`. Pipeline settings: `naming_convention="direct"`, `max_table_nesting=0`, no `_dlt_*` columns or tables, `pipelines_dir` under `~/.mlb/dlt` (outside the repo and outside the database), schema contract `columns: evolve` so a new field flows through and is reported. Alternatives: `dlt`'s `rest_api` declarative source for plain REST sources (use where it fits, e.g. cursor-paged Polymarket catalog); hand-written resources where the fetch is windowed or scraped.

**D3. The destination is ours (custom destination), not `dlt`'s built-in Postgres.**
`dlt` hands each batch to a project-owned destination that applies the existing landing rule for that table, chosen from a small per-table policy list: scoped replace (`load_dataframe`), append-only typed (`market_store.append_rows`), upsert, or truncate-and-reload. The destination also writes the `meta.ingestion_item` ledger row for the item. Why not the built-in Postgres destination: it would create `_dlt_*` tables and its own merge rules, infer types (the 150 GB market tables were fixed precisely because raw stays text or deliberately typed), and make `dlt` state the authority, which is the ADR-300 objection.
*Gate (task 1.x spike, decide before migrating anything):* prove that one ledger item's rows and its ledger row commit in one transaction from the custom destination, with `max_parallel_load_jobs=1` per item or `batch_size=0` file-path jobs. *Fallback if it cannot:* run `pipeline.extract()` and `pipeline.normalize()` only, and read the normalized files from the load package in our own loader, one transaction per item. `dlt` stays the engine in both; only the hand-off point changes.

**D4. The ledger and rights stay ours; `dlt` state is a cache.**
`meta.ingestion_item` records done/unavailable/failed; `source_profiles.py` gates exports. Deleting `~/.mlb/dlt` must cost only a re-check (spec: "tool state is lost"). `mlb doctor` reports whether the state directory exists but never fails on it.

**D5. Downloads of files stay in `manifest.py`; `dlt` reads the kept files.**
For file sources (Retrosheet zips, Lahman, Chadwick register, Savant CSVs) the download stage is `manifest.download` (hash, URL, retrieval time, replay), and the `dlt` resource reads the kept path. For Retrosheet events the Chadwick parse remains between the two. Why: replay without network is a spec requirement, and `manifest` already does it.

**D6. Rate limiting and process sharding stay ours where they are tuned.**
Polymarket's backfill is tuned to 90 requests/s over 4 processes x 4 threads (`shard.py`, `RateLimiter`); Kalshi to 16/s. `dlt`'s thread parallelism is used inside a process, but the cross-process sharding and the shared limiter remain, wrapped around the `dlt` resource. Measured in the spike (`results.md`): `dlt` is about 1.4x slower than the current price loader, outside the 10% rule, so by this rule the bulk market and Retrosheet/Statcast backfills keep their present fast load path until a full-scale measurement passes; `dlt` takes catalogs, incremental updates and every source whose size makes the fixed ~0.15 s per run irrelevant. The destination lets one run carry many ledger items to absorb that fixed cost (D10).

**D7. Migration order (default, owner may reorder).**
1. `register`, `lahman` (single CSV files, whole-file replace; proves the replace policy and the provenance fields with the least risk). 2. Polymarket and Kalshi catalog and snapshots (cursor paging is the clearest `dlt` gain), then price history incrementals on the typed tables from `stabilize-and-market-store` (bulk backfill stays on the fast path, D6). 3. Retrosheet family (artifact plus Chadwick). 4. `statcast`, `statcast_leaderboard`, `bref`, `fangraphs` (scrapers; the FanGraphs user-agent exemption of ADR-288 stays in its download stage). 5. `news`. 6. `mlb_api` last, split by endpoint family (3,606 lines, 5-minute cron, the largest write source).

**D8. Dependency and version.** `dlt` is added with a version range (`>=1.21,<2`, Apache-2.0), without database extras because the destination is ours. Pinned in `uv.lock`; upgrades go through the same parity check.

## Risks / Trade-offs

- [Custom destination cannot commit rows and ledger together] -> D3 gate and fallback; decided before any migration.
- [`dlt` throughput below the tuned market loaders] -> D6 measurement; keep the present fetch for those two if needed.
- [Another layer to learn and debug] -> the three stage interfaces are small; every migrated connector's sidecar says which `dlt` features it uses.
- [`dlt` changes naming or schema behavior in a release] -> `direct` naming and a pinned range; parity tests run in CI against fixed captured payloads.
- [Two paths per connector during migration] -> accepted by design; the old path is removed only after 7 clean runs and owner approval (spec: connector-migration).
- [Scope creep into `mlb_api`] -> it is last and split by endpoint family; each family is its own step.

## Migration Plan

Spike and gate first (nothing on production). Then per source: build the `dlt` path beside the old one, run both on a fixed range into scratch tables, compare, record in `results.md`, switch the `mlb ingest` mode to the new path behind a setting, watch 7 runs, retire the old path with approval. Rollback at any point before retirement: flip the setting back. The ADR superseding ADR-300 is written when the owner approves the spike result.

## Open Questions

- Whether `dlt` state should also be mirrored into `meta.*` for visibility (can wait; the ledger already covers correctness).
- Whether the free `dlt` verified sources add anything for sources we already scrape (check per source when its step starts; no new source is added by this change).

**D9. Type contract: one declared schema per table, cast with polars, rejects kept.** (From the Opus review of the spike.)
Each landed table has one pyarrow schema in `ingest_layer/types.py`, built from `market_store.Column`/`MarketTable` (no second registry). A test compares every schema with `information_schema.columns` and `mlb doctor` reports a mismatch. At ingest a polars step turns empty strings into NULL (never zero), casts with `strict=False`, and marks a row rejected where the source text is non-empty but the cast gives NULL; rejected rows go to the table's reject table as source text in the same transaction. An unknown new source field is landed as text and reported (schema-watch). The CSV copy path needs a test that proves empty versus NULL survives Arrow's quoting.

**D10. Destination rules the spike did not prove.**
(a) One pipeline name and state folder per item, or `abort_packages()` before every run, so a leftover failed package can never be written under another item's ledger row; tested with a shared state folder. (b) One run may carry many ledger items, each with its own ledger row, in one transaction. (c) Landing policies (scoped replace, append-only, upsert, truncate-and-reload) are in the destination, including an item with zero rows (replace still deletes; ledger row still written, because dlt may call nothing). (d) The ledger row stores rows actually inserted, not rows offered, and fills `source_url`, `artifact_sha256`, `run_id`, `schema_fingerprint`; `retrieved_at` is download time, not load time. (e) An item that writes two tables is one transaction, not one per file. (f) `mlb doctor` reports pending dlt packages. (g) Rollback: until a source is retired the old path stays runnable, and a parity difference found after the switch reverts the setting, not the data.
