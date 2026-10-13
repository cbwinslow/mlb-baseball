# Proposal

## Why

Every connector under `mlb_baseball/connectors/` mixes downloading, parsing and loading in one module (`mlb_api.py` alone is 3,606 lines; the others each re-implement paging, retries, window planning, schema drift and loading). That makes any one piece hard to measure, upgrade or replace, and it is behind the recurring ingestion problems (silent failures, long nightly runs, full rewrites of unchanged data, 150 GB of untyped market text). The owner wants download and ingestion built from separate, replaceable parts, using established tools (`dlt`) instead of per-source hand-written plumbing, so that changing one tool or one source cannot break the rest.

## What Changes

- **Three separate stages with narrow interfaces:** *download* (fetch and keep the source artifact or response, with hash and provenance), *load* (land rows in `raw`), *check* (ledger, rights profile, health). A source is a small adapter that plugs into the stages; no stage imports another's internals.
- **`dlt` becomes the standard tool for the download/extract/normalize side** of new and rewritten sources (paging, retries, incremental cursors, schema contracts). It runs with names kept exactly as the source gives them (`naming_convention="direct"`, no nested sub-tables) so `raw` stays source-faithful.
- **Our own loader stays the destination.** `dlt` hands rows to a project-owned custom destination that applies the existing landing rules (scoped replace or append-only, typed market tables, reject tables, `meta.ingestion_item` ledger, per-source rights profile). `dlt`'s own state is a cache; the ledger remains the record of what is done.
- **Sources move one at a time** in an agreed order, each with a parity check (old and new loader produce identical rows for the same input range) and a rollback (the old connector stays callable until the owner retires it).
- **Supersedes ADR-300** (which rejected `dlt`). Written as a new ADR with the reasons the decision changed, once the owner approves.
- **Folds in** the `dlt` pilot from `stabilize-and-market-store` (its task 2.7d): the market loaders are the first migration, on top of the typed tables and `market_store` already built there.
- **BREAKING:** none for readers of `raw`; table and column names stay. Operators keep the same `mlb ingest <source>` commands.

## Capabilities

### New Capabilities
- `ingestion-stages`: how a source is split into download, load and check stages, what each stage must provide and may not know, and that `dlt` is the standard extract/normalize tool with project-owned loading and ledger.
- `connector-migration`: the rule for moving an existing connector onto the stages: one source at a time, parity evidence first, old path kept for rollback, no change to raw names or rights profile.

### Modified Capabilities
<!-- None: no existing spec's requirements change. `market-price-store` (in stabilize-and-market-store) already requires staging, casts and append-only loads, which the custom destination reuses. -->

## Impact

- Code: new `mlb_baseball/ingest_layer/` (stage interfaces and the custom `dlt` destination, wrapping `load.py`, `market_store.py`, `manifest.py`, `ingest.py`); each connector migrated in turn (`polymarket.py`, `kalshi.py` first). `registry.py` keeps its explicit dispatch.
- Dependencies: `dlt` (Apache-2.0) added; per-source optional extras only where a source needs them.
- Docs/ADR: new ADR superseding ADR-300; `docs/ARCHITECTURE.md` connector contract; `.dox.md` sidecars of each migrated connector; `docs/SOURCE_RIGHTS.md` unchanged unless a rights profile changes.
- Database: no new schema for the layer itself; `dlt` is configured not to create `_dlt_*` tables in `raw`/`core`/`gold`.
- Out of scope: replacing the Chadwick tools (ADR-299), changing `core`/`gold`, SQLMesh, incremental `conform`, any new data source, any paid service.
