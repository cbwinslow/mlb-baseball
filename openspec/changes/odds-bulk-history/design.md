## Context

Evidence is in `proposal.md`. Existing code: `polymarket.backfill_history()` (one token at a time, per-market commit), `kalshi.backfill_history()` (live endpoints only), `meta.ingestion_run` / `meta.ingestion_item` (`ingest.track_run`, `record_items`), `net.call_with_retry`. The Polymarket fix to use explicit windows is already merged (#318); this change builds the fast, complete version on top.

## Decisions

**D1. Official endpoints are the source of truth; bulk datasets seed and cross-check.** Becker/SII data is third-party, trade-level, and its freshness is not ours to control. It cannot replace per-token price series for settled markets, and a rights row is required first. It is loaded only into separate raw tables.

**D2. Polymarket: batch + bounded parallelism.** `POST /batch-prices-history` (20 tokens), windows <= 14 days, N workers (start at 4, raise only with measured headroom) sharing one rate limiter set well under 1,000 requests/10 s. Order: market `startdate` descending. Worker results are written by one writer (single connection, per-batch commit) so database locks stay simple.

**D3. Ledger item = (source, dataset, item_key)** with `item_key = <market>:<window_start>` so each window is skipped, retried or replaced on its own. Empty windows are recorded `empty`, which is what makes a rerun cheap (the 4-hour run left no record of the empty tokens, which is why progress was unreadable).

**D4. Kalshi cutoff handling.** Fetch `/historical/cutoff` once per run; pull historical markets (cursor, 1000/page) then live; key rows by ticker; candlesticks and trades from the endpoint matching each market's settlement versus the cutoff. Discover series from `GET /series` filtered to baseball rather than a fixed list. Budget: Basic tier 200 read tokens/s (10 per request, ~20 requests/s); use 10 req/s to leave margin.

**D5. Run tracking is columns plus a progress writer, not a new framework.** Add to `meta.ingestion_run`: `items_planned`, `items_done`, `requests`, `last_progress_at`; to `meta.ingestion_item`: `duration_ms`, keep `attempts`, `error`. A small progress helper in `ingest.py` updates the run row at most once a minute. This is the same run/asset model Dagster and OpenLineage use, without adopting their runtime. `pg_stat_statements` covers query timing; `pg_profile` and `pg_wait_sampling` (available on this server) are adopted only if a measured question needs them (task 5.6). The host's OpenTelemetry collector is a possible later export target, not a dependency.

**D6. Sizing before loading trades.** Polymarket trades total about a billion rows; the plan sizes disk and load time for the MLB-tagged subset first (markets under `sport` events), recent first, and records the decision with numbers.

## Risks / Trade-offs

- Batch endpoint limits come from docs summaries; task 1.1 verifies the limits live (token count, window, rate headers, error shape).
- Parallel workers raise the chance of throttling: back off on 429 and log it.
- Third-party datasets may be stale or differ in definitions; they are labeled, not merged.
- Running two ingests together hit the workflow lock; the backfill takes the lock for hours. Task 3.4 decides whether history backfill uses its own lock name so `mlb build` and the nightly are not blocked.

## Open Questions

- Which Polymarket tokens matter (all 435k vs. moneyline only)? Default: all, newest first; the ledger lets us stop any time.
- Trade-level data: data-api per-trade pagination limits (verify in 1.1) versus the on-chain datasets.
