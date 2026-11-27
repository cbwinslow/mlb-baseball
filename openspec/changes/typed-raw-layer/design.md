## Context

Measured 2026-10-13 (read-only on production): `raw` = 150 tables, 206 GB. Largest: `polymarket_price` 110 GB and `kalshi_candle` 40 GB (typed by `stabilize-and-market-store`), `retrosheet_plays` 20 GB (179 columns, 178 text), `retrosheet_event` 13 GB, `statcast_pitch` 10 GB (121 text columns), then everything else under 3.1 GB. The production disk has 165 GB free; `cbwsff1` (16 cores, 14 GB RAM, 845 GB free, Docker with Postgres 16) is the test server. `mlb_test` on the main server is free to destroy and recreate.

## Decisions

**D1. Declare, don't guess.** `infer.py` proposes a type per column from real data (narrowest type that holds every value exactly; leading zeros, mixed values and empty columns stay text). The reviewed JSON is the declaration. Overrides are explicit (for example a column that is a code, not a number).

**D2. Strict by default for snapshots; reject tables for streams.** A value that breaks its declared type stops a snapshot load (`land(strict=True)`). Streaming/market tables keep the reject-table path from `market_store`.

**D3. Two retype methods.** (a) *Beside and swap* for tables up to a few GB: load typed `<t>__new` from the kept source files, compare, rename in one transaction (`<t>` -> `<t>__old`, `<t>__new` -> `<t>`). (b) *In place* for the very large tables where a second copy does not fit: `ALTER TABLE ... ALTER COLUMN ... TYPE ... USING`, after a full-scan check that every value casts, on a restored dump first. Source files are not always kept (APIs), so (b) is the default for API-sourced tables.

**D4. Values that the old path corrupted are repaired from the source, not carried over.** In-place conversion keeps a NULL that was really `NA`; where the source is kept, reload and compare; where it is not, report the affected columns.

**D5. Backup first.** Before any production swap: `pg_dump` of the affected tables to `cbwsff1` (or a dated file under `backups/`), size and restore verified once.

**D6. Rehearse on `cbwsff1`.** Restore a production dump (raw + whatever readers need) into a Postgres on `cbwsff1`, run the exact retype, run the integration suite against it, record timings and disk use. Production runs the same commands.

**D7. Readers first.** For each retyped table list every reader (`grep` plus the dependency catalog), fix SQL that does `NULLIF(col,'')::int` or compares text to integers, and cover each with an existing or new test before the swap.

**D8. Order.** Lahman and register (31 tables, ~1.2 M rows) -> small API/file tables -> Polymarket/Kalshi (handled by `stabilize-and-market-store`) -> Statcast -> Retrosheet. One table family per step.
