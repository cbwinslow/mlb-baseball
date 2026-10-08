# Operational Milestone: Kalshi and Polymarket history backfill

**Date:** 2026-10-08
**Target database:** PostgreSQL `mlb` (production)
**Change:** `openspec/changes/data-completeness` task 2.5

## Actions
1. Fast-forwarded the main checkout to `origin/main` (owner edits left untouched).
2. `mlb ingest kalshi --mode backfill`, twice (the second pass picked up markets opened during the first and retried 2 failed markets).
3. `mlb ingest polymarket --mode backfill`, twice (same reason).

## Results
- Polymarket: about 147M price rows added over two passes; `mlb coverage --unexplained --source polymarket` reports nothing.
- Kalshi: candles added for every market opened since the earlier backfill; `mlb coverage --unexplained --source kalshi` reports nothing.
- Data disk had 707 GB free after the runs.

## Review the same day
All held series and events are MLB. Only game-winner markets reach `core.market`; props, futures and price history are kept for later research (owner decision: keep all). Source pages `docs/sources/kalshi.md` and `polymarket.md` were re-probed and corrected (PR #382).

## Open
No schedule runs the backfills, so new markets will accumulate again (task 3.3).
