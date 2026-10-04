## Context

Observed in code: `kalshi._run` and `polymarket._run` each do a full catalog pull, replace the catalog tables with `load_dataframe` (TRUNCATE), then append a snapshot with `append_dataframe`. Snapshots already exist and are append-only (ADR-049) but only run inside `mlb nightly`. `backfill_history()` exists for both sources (scoped-replace per ticker / token) and was never run. An existing pattern for a light cron job is `scripts/mlb_api_update.sh` (every 5 min there, `flock`). See proposal.md for motivation.

## Goals / Non-Goals

**Goals:** frequent append-only odds history; no silent loss of catalog rows; backfill run once; tests first.
**Non-Goals:** new sources, trading/authenticated calls, canonical game matching (stays in `conform`), model use of odds, redesigning other connectors.

## Decisions

1. **Separate capture entry point per source (`mlb ingest <src> --mode snapshot`).** Fetches open markets only and appends snapshots. Alternative: shorten the nightly interval — rejected, it re-pulls the whole catalog and ties capture to a 2-hour run.
2. **Own cron script modelled on `mlb_api_update.sh`** (own lock, own log, every 15 min, skip when no games are scheduled). Alternative: SQLMesh/other scheduler — rejected, ADR-016 already settles cron + flock.
3. **Catalog tables keep rows: replace only the keys that were fetched.** Verified in `mlb_baseball/load.py`: `replace_dataframe_scopes` already does DELETE-by-key + COPY, so rows absent from a pull stay, and every table already has `_loaded_at`, which then means "last seen". No new helper, column or migration is needed (this replaces the earlier `last_seen_at` idea). Keys: Kalshi series `ticker`, event `event_ticker`, market `ticker`; Polymarket event `id`, market `id`, outcome `market_id`. Alternative: a full history table of every version — rejected as heavy (364k Kalshi market rows); price history already lives in snapshots.
4. **Backfill code unchanged unless a test fails;** it is only run once under owner approval. It stays out of routine updates.
5. **Doctor:** replace "table does not exist" with "backfill not run" state; add a gap check from snapshot timestamps.

## Risks / Trade-offs

- Snapshot volume. Measured 2026-10-04: one capture = 3,008 Kalshi + 5,314 Polymarket rows (all open markets, including futures and props). At 5 minutes that is about 2.4M rows/day, too heavy, so the cadence is **15 minutes, only on days with scheduled games** (about 0.4M rows/day in season). Re-measure after one week; a change-only capture is the next step if still heavy.
- Rate limits on the public APIs → keep existing retry and politeness controls; capture is one small request set per tick.
- `track_run` writes one `meta.ingestion_run` row per tick (~288/day per source) → measure; if noisy, capture logs to its own table instead.
- Upsert with no delete leaves stale open-looking markets → consumers use snapshots and market status, not catalog presence.
- Source quirks (Kalshi `max candlesticks: 5000`, Polymarket keyset pagination) are already handled; do not regress (see `.dox.md` files).

## Migration Plan

Merge tests+code first (no production writes). Then, each owner-approved and logged in `pipeline-recovery/results.md`: apply any migration, install the cron entry, run the two backfills. Rollback: remove the cron line; tables are additive.
