# Proposal

## Why

The nightly pipeline now takes about 3 h 43 min (2026-10-11: update 18, conform 82, report 15, predict 50, coverage 35, repair 23 min) and ends with a failure code almost every night, so a failure no longer gets attention. Part of the cause is that loaders rewrite data that has not changed (the 5-minute `mlb_api` tick reloads about 60,000 unchanged `mlb_transaction` rows; Retrosheet files are force-reloaded nightly), which produces about 44 GB of WAL a day on a spinning RAID. Separately, `raw.polymarket_price` (110 GB, 604M rows) and `raw.kalshi_candle` (40 GB, 213M rows) are 150 GB of the 235 GB database, stored almost entirely as `text`. An independent review (Opus 5.5, 2026-10-12; see `design.md`) ranked these as the first things to fix.

## What Changes

- **Stabilize the nightly run (Phase 0):** working failure alerts and a "did it finish?" watchdog; pipeline failure separated from data-health warnings; coverage made cheap (`--light`, already on `main` via ADR-303); loaders skip a load when the source content is unchanged (content hash or Last-Modified); the 5-minute tick limited to live games and today's schedule.
- **Market price store (Phase 1):** retype and compress `raw.polymarket_price` and `raw.kalshi_candle` (and the snapshot tables) inside PostgreSQL using TimescaleDB, keeping table names and column names, with a 30-minute scratch-database test first. Polymarket and Kalshi data stay together in one store.
- **Loader pilot:** the rewritten market loaders are the pilot for `dlt`, keeping `meta.ingestion_item` and the source-rights profiles as the owners of ledger and rights.
- **ADR changes (drafts for owner review, in `design.md`):** relax ADR-300 (no `dlt`) to a per-source pilot; record the TimescaleDB decision.
- **BREAKING:** none intended. The old tables are kept as `_old` for 7 days and can be renamed back.

## Capabilities

### New Capabilities
- `nightly-health`: what the nightly run must do when a step fails or hangs, and how pipeline failures differ from data-health warnings.
- `market-price-store`: how Polymarket and Kalshi price history is stored, typed, loaded and kept together.

### Modified Capabilities
<!-- None: no existing spec's requirements change. -->

## Impact

- Code: `mlb_baseball/nightly.py`, `scripts/mlb_daily_update.sh`, `scripts/mlb_api_update.sh` (crontab entries), `connectors/mlb_api.py`, `connectors/retrosheet_event.py`, `connectors/polymarket.py`, `connectors/kalshi.py`, coverage/repair commands.
- Database: new typed hypertables for the two market tables (a migration), a reject table per source, `_old` copies for 7 days. Production `mlb` is touched only after the scratch test and per-step owner approval.
- Dependencies: `dlt` added for the pilot loader only.
- Docs: `docs/DECISIONS.md` (new ADRs), `.dox.md` sidecars for touched files, a `changelog/` entry for each production change.
- Out of scope: renaming schemas, incremental `conform`, the Polars/DuckDB feature work, the live in-game service, Prefect, Redis, ClickHouse. Each is a later change; ClickHouse is the fallback only if the Timescale test fails the exit criteria.
