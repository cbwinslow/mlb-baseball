# Design

## Context

Evidence, tagged V (checked in this session) or A (assumed). Source: an independent read-only review by Opus 5.5 on 2026-10-12, with the main points re-checked by the main session.

- Nightly 2026-10-11 ran 06:00 to 09:43 UTC and ended rc=1; coverage (35 min) and schema-watch fail every night [V `logs/mlb_daily_update.log`]. `MLB_ALERT_COMMAND` is unset so alerts only reach the log [Opus V].
- `pg_stat_wal`: 146 GB since 2026-10-08; the 5-minute `mlb_api` tick reloads about 60k `mlb_transaction` rows each run, the biggest single WAL writer [Opus V `pg_stat_statements`].
- `raw` is 4,897 of 5,049 columns as `text`; `core`/`gold` are already mostly typed [V]. The two market tables are 150 GB of 235 GB [V].
- `/mnt/storage` (Postgres data volume) has 690 GB free [V]. Disks are spinning (RAID5) [Opus V].
- TimescaleDB 2.28 and `pg_duckdb` are installed in `mlb` [V]. Local ClickHouse is 25.8 LTS [V].
- Sample of 924k Polymarket rows compressed to 0.93 bytes/row in ClickHouse-local [Opus V]. Timescale columnar compression is estimated at 2-8 bytes/row, i.e. 1.5-5 GB for Polymarket [A, to be measured in task 2.2].
- Nothing downstream reads the two market tables except the connectors, coverage and repair; no views or feature SQL [Opus V].

## Goals / Non-Goals

**Goals:**
- Nightly under 2 h, WAL per day down at least 40%, and a failure always produces an alert.
- The two market tables total 10 GB or less, typed, same names, one store.
- A `dlt` loader running in production for one market feed.

**Non-Goals:**
- Incremental `conform`, the Polars/DuckDB feature work, the live in-game service, Prefect, Redis (later changes).
- Renaming schemas or changing `core`/`gold` structure.
- Deciding which predictions are needed next season; the owner chose to keep that open and easy to change, so nothing here removes any model or feature.

## Decisions

**D1. Timescale in PostgreSQL first; ClickHouse is the fallback.**
Why: keeps all market data in one transactional store next to `core` (owner wants it together) and needs no new service. Alternative: ClickHouse (smaller and faster in the sample, but a second engine and cross-database joins). The scratch test (task 2.2) decides; if compressed size is over 10 GB or a per-token range query is too slow, this change stops and the owner chooses between more Timescale tuning and ClickHouse.

**D2. Retype by building a new table and swapping, never `ALTER TYPE` in place.**
Why: in-place retype rewrites 110 GB on spinning disks while holding a lock. Build `_new` as a hypertable, copy by month chunk in `ts` order, compress each chunk right after, catch up rows loaded after the copy started, then swap with two renames in one transaction while the backfill is paused. Keep `_old` for 7 days.
Types: Polymarket `clob_token_id text`, `_market`/`_event int`, `ts bigint`, `price double precision`; Kalshi `*_dollars numeric(10,4)`, `ts bigint`. `ts` stays bigint so `"ts"::numeric` predicates keep working. Empty string becomes NULL, never 0.

**D3. Bad values go to a reject table, not an abort.**
Per-chunk regex checks find values that will not cast; they are written as text to `raw.polymarket_price_reject` / `raw.kalshi_candle_reject`.

**D4. Loader writes append-only through a text staging table.**
COPY into a TEMP text table, then `INSERT ... SELECT` with casts and `ON CONFLICT DO NOTHING`. This replaces the `DELETE ... "ts"::numeric >= $2` path.

**D5. `dlt` pilot on the Polymarket price loader, ledger stays ours.**
`dlt` provides the paging, retries and schema checks. `meta.ingestion_item` stays the ledger of record and the per-source rights profile still gates exports, so `dlt`'s own state is a cache and not a second source of truth. Parity check: the same token range loaded by the old and the `dlt` path must produce identical rows. Alternative: keep the hand-written loader (rejected for this one loader because it is being rewritten anyway).

**D6. Failure and health are separate signals.**
Nightly exit code = pipeline steps only. Data-health findings go to a daily digest. Coverage and repair run weekly and read statistics or the ledger, not row counts.

**D7. Skip unchanged loads by content hash / Last-Modified.**
Applies to the Retrosheet force-reload (`retrosheet_event.py:256-273`) and the `mlb_api` transaction/roster/draft loads (hourly, skipped when unchanged). The 5-minute tick keeps only live games and today's schedule.

### ADR drafts (owner review; numbers assigned on approval)
- **Relax ADR-300:** `dlt` is allowed per source after a parity check; migrating the other connectors needs its own evidence. Revisit if the pilot shows `dlt` state diverging from `meta.ingestion_item`.
- **New: market data in TimescaleDB.** Decision D1 with the scratch-test numbers filled in. Revisit if size or query time misses the targets.
- The older "not adopting TimescaleDB" statement is superseded by the new ADR (to be located and cited when written).

## Risks / Trade-offs

- [Swap during an active backfill] -> pause the backfill first; catch-up step for rows loaded after copy start.
- [Copy generates about 50-60 GB of WAL (assumed)] -> throttle per chunk; 690 GB free; run off-hours; measure on the first month before continuing.
- [Compression ratio lower than estimated] -> measured in the scratch test before any production work; exit criteria stop the change if missed.
- [Weekly-only coverage hides a gap for a week] -> the daily digest still reports ledger-based freshness.
- [Spinning RAID shared with other services (langfuse, datahub)] -> schedule the copy away from the 06:00 nightly.
- [Alert channel not yet chosen] -> task 1.1 asks the owner; until set, `mlb doctor` reports "no alert channel".

## Migration Plan

1. Scratch test (no production change). 2. Phase 0 changes behind config, one at a time, each reversible by reverting config or cron. 3. Production market-table build as `_new`, verify, swap, hold `_old` 7 days, drop only with owner approval. Rollback at any point before the drop: rename `_old` back.

## Open Questions

- Which alert channel (ntfy, email, other)? Needed before task 1.1 completes; does not change the specs.
- Should the snapshot tables (`kalshi_snapshot`, `polymarket_snapshot`) be retyped in this change or the next? Default: this change, after the two large tables, only if the first swap meets the exit criteria.
