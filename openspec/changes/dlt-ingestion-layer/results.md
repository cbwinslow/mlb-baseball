# Spike results (tasks 1.1-1.4)

Measured 2026-10-13 in a disposable test database, no network, no production access.

## 1.2 One-item hand-off: works
A `dlt` custom destination (`mlb_baseball/ingest_layer/destination.py`) with `batch_size=0` and
parquet files gets one file per table per pipeline run. It reads the file with pyarrow and, in one
PostgreSQL transaction, copies the rows into the target (`ON CONFLICT DO NOTHING`) and upserts the
`meta.ingestion_item` row. Tests (`tests/integration/test_ingest_layer_destination.py`):
- rows and ledger row land together; a second run changes nothing;
- a bad value mid-item leaves neither rows nor a ledger row;
- a ledger failure after the rows were inserted rolls the rows back.

So the fallback in 1.3 is not needed. One loader per ledger item (one pipeline run per item).

Things the spike found that the design must carry:
- `dlt` adds `_dlt_load_id` / `_dlt_id` columns; the destination drops every `_dlt_*` column.
- A failed load package stays pending and is retried by the next run of the same pipeline;
  after a failure call `pipeline.abort_packages()` (`drop_pending_packages` is deprecated).
- `polars` standard wheel crashes on this server (no AVX2, SIGILL); the project uses
  `polars-lts-cpu`.
- Importing `tests.conftest` from a test hangs the run; take connection details from `db_conn.info`.

## 1.4 Overhead against the current Polymarket price loader
100,000 rows in 10 batches of 10,000 (20 tokens x 500 points), real PostgreSQL, same table shape.

| Path | rows/s |
| --- | --- |
| current (`market_store.append_rows`, CSV text, staged checks) | ~31,000 |
| dlt, Python dicts in | ~10,000 |
| dlt, pyarrow table in (polars `to_arrow()`), row-by-row COPY | ~20,000 |
| dlt, pyarrow table in, Arrow CSV COPY | ~22,000 |

`dlt` alone (no database): dicts 13-19k rows/s, Arrow 66k (10k rows) to 430k (100k rows) rows/s;
fixed cost about 0.15 s per pipeline run. Conclusion: pass typed Arrow/polars batches to `dlt`,
never Python dicts; the remaining gap to the current loader (about 1.4x slower) is the fixed
per-run cost plus the staging copy. The current loader's value checks (reject table) are not yet
in the dlt path; they are task 3.1.

## Gate outcome
Owner accepted the gate on 2026-10-13. Rule D6 (within 10%) is not met by 1.4x, so bulk backfills stay on the fast path for now; Opus review changes are D9, D10 and the reordered D7. The benchmark must be repeated with reject checks in both paths and a reused state folder (task 2.0).

## Repeat after the Opus review (tasks 2.0 / 2.0b)
New `ingest_layer/land.py` + `types.py`: type cast and reject handling now run in the dlt path too, `dlt` only
normalizes to files and the database is written once, in one transaction, after `dlt` finishes. Same 100,000
polymarket-shaped rows, source values as text in both paths, reject checks in both:

| Path | rows/s |
| --- | --- |
| current loader (`market_store.append_rows`) | ~30,000 |
| dlt layer, one call per 10,000-row item | ~16,000 |
| dlt layer, ONE call carrying 10 items (100,000 rows) | ~36,000 |

The gap was the fixed cost per call, not the data work. With many items per call the layer is faster than the
current loader, so rule D6 (within 10%) is met for batched work; single small items still pay ~0.15 s each, so
callers batch items (D10b). Bulk backfills can be re-measured at full scale before they are moved.

## Task 4.1: register and lahman parity (scratch tables, synthetic files)
`tests/integration/test_ingest_layer_sources.py`. Same rows as the old loaders. Differences, all intended:
- Lahman: the old path lets pandas infer types, so an integer column with a blank becomes `1934.0` and `007` becomes `7.0`; the new path keeps the source text (`1934`, `007`). Any later conform step that depended on the `.0` text should be checked when Lahman is switched (task 4.2 owner step).
- Register: all four tables replaced in one transaction; a failure part-way publishes nothing (tested), same as before.
- Ledger: both now write one `meta.ingestion_item` row per table with URL and file hash (Lahman); the old path wrote none.
Not yet run: the full real Lahman and register files (no Lahman zip is held locally; the register is fetched from GitHub). Do that on scratch tables before the switch.

## Real-data check, 2026-10-13 (Lahman 2025 release from github.com/cbwinslow/lahman-database-csv, Chadwick register from GitHub)
Landed typed into scratch tables in `mlb_test` and compared value by value with production (read-only).
- Lahman: 706,466 rows, 27 tables, 31 s, no row failed its declared type. Production already holds the 2025 release (same row counts in every table), so it is not frozen at 2021.
- The only differences from production are the old loader's: 3,336 cells where the source says `NA` (league code of the National Association, "not active" flags) are `NULL` in production, and integers with blanks are text like `1934.0`. After mapping `NA` to NULL there are zero differing rows in all 27 tables.
- Register: 526,894 people + 1,346 names + 27,340 links + 249 countries, 33 s; zero differing rows against production.
- Types: Lahman 237 integer, 6 double precision, 4 date, 130 text columns; register people 24 integer columns. Schemas are in `ingest_layer/schemas/`.
