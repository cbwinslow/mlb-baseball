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
