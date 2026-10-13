## Why

Production `raw` is 206 GB in 150 tables with 4,897 text columns and 152 typed ones. Text everywhere costs storage and speed, makes every reader cast, and hides data bugs: the old pandas path turned the source text `NA` into NULL in 3,336 Lahman cells and wrote `1934.0` for integers. The owner wants optimized types, enforced at ingest by the `dlt` + pyarrow + polars layer, and the existing tables converted (ADR-304).

## What Changes

- Every `raw` table gets a declared schema (`mlb_baseball/ingest_layer/schemas/<source>.json`), proposed from real data by `ingest_layer/infer.py`, reviewed, committed.
- Existing tables are retyped in tiers, smallest and simplest first: Lahman and register (done in scratch, verified), then the small API/file tables, then the large ones (Retrosheet, Statcast, the market tables already in `stabilize-and-market-store`).
- Each table is retyped by: back up, load the typed table beside the old one (or in-place `ALTER ... USING` when the table is too large to duplicate), compare value by value, swap names in one transaction, keep the old table until the owner approves dropping it.
- Every reader (conform SQL, reports, export, health, `mlb_api`, field census, coverage) of a retyped table is inventoried and fixed first.
- A full rehearsal of the big tables runs on the `cbwsff1` test server from a production dump before anything runs on production.

## Impact

Touches production data (owner approval at each swap, backup first), `conform` SQL, reports. No change to source rights or the PIT rules. Supersedes the all-text raw rule in `load.py.dox.md` (ADR-304).
