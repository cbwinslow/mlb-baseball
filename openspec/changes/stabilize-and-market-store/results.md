# Results

## 2.2 Timescale scratch test (2026-10-12)

Target database: `scratch_ts_test` (created on the production server, nothing from production `mlb` was written). Sample CSVs exported read-only from production by the Opus review. TimescaleDB 2.28, hypertable chunks of 30 days on `ts` (epoch seconds, bigint), compression segmented by token/ticker, ordered by `ts`.

| Table (sample) | Rows | Uncompressed | Compressed | Bytes/row |
|---|---|---|---|---|
| Polymarket price (60 tokens, 2025-09-14 to 2026-10-11) | 923,757 | 147 MB (about 159 B/row) | 3.1 MB | 3.47 |
| Kalshi candle (9 of the 32 columns, `numeric(10,4)`) | 774,104 | 90 MB | 4.6 MB | 6.21 |

Per-token range query on the compressed Polymarket data: 166,161 rows in 37 ms; whole-token scan (184,273 rows) in 22 ms.

Extrapolation (estimate, not measured on production): Polymarket 604M rows x 3.5 B = about 2.1 GB; Kalshi 213M rows x 6.2 B = about 1.3 GB on 9 columns, likely 3-4 GB with all 32 columns. Total about 5-6 GB against the 10 GB target, down from 150 GB.

Caveats: the sample is 60 tokens, so real chunks hold many more rows per token (usually compresses better, but not tested); Kalshi sample covers 9 of 32 columns; the sample CSVs had no bad values, so reject-table behavior is untested here (task 2.4).

## 2.3 Decision gate

Passed provisionally: projected size is within the 10 GB target and range queries are fast, so ClickHouse is not needed for this change. Re-check after the first production month-chunk in task 2.6; if it misses the target, stop and ask the owner.

## Scratch database

`scratch_ts_test` still exists (small). Dropping a database forces a Postgres checkpoint, which stalls a running backfill, so it is left in place until the owner says to drop it.

## 2.1 Reader inventory (2026-10-13, read-only)

Method: production `mlb` catalog queries in a read-only session (`pg_depend`/`pg_rewrite`, `pg_trigger`, `pg_constraint`, `pg_index`, `pg_proc.prosrc`) plus a repo search (`*.py`, `*.sql`, `*.toml`, `*.sh`, `*.yaml`; docs and archived changes ignored for behavior).

**In the database:** no view, materialized view, trigger, foreign key or function references either table. Each table has one index only: `polymarket_price_clob_token_id_idx` (7.2 GB) and `kalshi_candle_ticker_idx` (2.3 GB). Sizes: `raw.polymarket_price` 110 GB (about 604M rows), `raw.kalshi_candle` 40 GB (about 213M rows).

**In the code (everything that touches the names):**

| Reader/writer | What it does | Effect of the retype |
|---|---|---|
| `connectors/polymarket.py` (`PRICE_TABLE`) | loads windows through the shared load helpers; `check_backfill_state` | rewritten in task 2.7 |
| `connectors/kalshi.py` (`CANDLE_TABLE`, `ensure_table`) | loads candles; creates the table dynamically as text with a `ticker` index | rewritten in task 2.7; must create the typed table when absent |
| `coverage/registry.py`, `coverage/model.py` | expected-versus-held from the market catalog and the ledger (`meta.ingestion_item`); date column `ts` | no table scan for the verdict; `ts` meaning kept |
| `repair.py` (`SAFE_REPAIRS`) | runs `mlb ingest kalshi\|polymarket --mode backfill` for gaps | unchanged (command names stay) |
| `conform.py` | comment only; it does not read either table | none |
| tests | `test_kalshi_load.py`, `test_polymarket_load.py`, `test_coverage.py`, `test_conform.py` (drops them as dynamic raw tables), `test_repair_plan.py` | tests create the tables as text; the loader rewrite must keep a path that works on a fresh database |

No SQLMesh model, feature SQL, gold table or notebook reads either table. Conclusion: the swap affects only the two connectors and their tests; no reader needs a change.

**Facts found that change the plan (for task 2.4/2.5):**
- Production `ts` is `text` (not numeric); design D2 already keeps the epoch-seconds meaning and types it `bigint`.
- `raw.kalshi_candle` has 33 columns: `ticker`, `ts`, `open_interest`, `volume`, 17 `*_dollars` price columns, and 12 older cent-valued `price_*`/`yes_bid_*`/`yes_ask_*` columns. D2 types only the `*_dollars` columns; `open_interest`, `volume` and the cent columns need a type decision (likely `bigint`/`integer`), settled by the bad-value scan in 2.4.
- `raw.polymarket_price` has 6 columns: `clob_token_id`, `_market`, `_event`, `ts`, `price`, `_loaded_at`.
- The shared load helper adds missing columns as `text` and COPYs straight in, so the new loaders must go through a text staging table (D4) rather than the shared helper.
