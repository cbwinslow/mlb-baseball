## Why

The owner wants every Polymarket and Kalshi price, market and trade record we can lawfully get, as far back as each site has it, as fast as the sites allow. Measured on 2026-10-05 (probed live, read-only):

- **Polymarket backfill was both slow and empty.** It asked for `interval=max`, which returns nothing for settled markets, and it walked 435,412 tokens (217,706 markets) one request at a time (~3 tokens/s). After ~4 hours it had data for 58 markets. The CLOB allows 1,000 requests/10 s without a key (docs.polymarket.com rate limits); we used about 3% of that. A batch endpoint (`POST /batch-prices-history`, up to 20 tokens per request) answered 20 tokens in 0.56 s.
- **Kalshi is missing everything before the live cutoff.** Our connector only calls live endpoints, which exclude markets settled before `GET /historical/cutoff` (2026-08-06). Historical endpoints exist, need no key, and show `KXMLBGAME` history from 2025-04-16 (7,868 markets) and `KXMLBTOTAL` from 2025-10 (21,402) while `raw.kalshi_market` holds about 1,736 game markets, all from July 2026 on. Kalshi's Basic tier allows about 20 reads/s.
- **Others already solved parts of this.** `jon-becker/prediction-market-analysis` (MIT; 36 GiB parquet of Kalshi and Polymarket markets and trades; indexers), `SII-WANGZJ/Polymarket_data` on HuggingFace (MIT; 107 GB, 1.1B on-chain trades, 268,706 markets), `warproxxx/poly_data` (Polygon events via HyperSync), `pmxt` (unified SDK), Dune curated tables (partly gated). None gives per-token price series for settled markets directly, so they complement, not replace, the official endpoints.
- **We cannot see how long ingestion takes or how far it got.** `meta.ingestion_run` stores start, end and a row count only; a 4-hour run had no progress record, and a stale run row has no throughput.

## What Changes

- **Polymarket history, fast and complete**: batched window fetch (20 tokens/request, windows of at most 14 days), a few parallel workers within the documented limit, newest markets first, one ledger row per market-window, resumable; plus all Gamma market/event fields and per-trade history from the public data API where the docs allow it.
- **Kalshi history, cutoff-aware**: read `GET /historical/cutoff`, page live and historical markets, candlesticks and trades for every `KXMLB*` series (and other baseball series found), newest first, within the tier budget, deduplicated across the cutoff.
- **Bulk datasets as a rights-checked seed and cross-check**: evaluate the Becker and SII datasets (licence, coverage dates, schema); if they pass, load each into its own `raw` tables with provenance, never merged into our own source tables, and compare overlap with what the official endpoints return.
- **Better run tracking**: per-run and per-item timing, row counts, attempts and throughput recorded in `meta`, a progress line during long runs, a doctor check for stuck or too-slow runs. Evaluate `pg_profile` / `pg_wait_sampling` for database-side history; `pg_stat_statements` is already installed; the host already runs an OpenTelemetry collector.
- No paid providers. No new orchestration framework unless a measured need appears.

## Capabilities

### New Capabilities
- `odds-history`: complete, resumable, rate-limit-aware historical ingestion of Polymarket and Kalshi markets, prices and trades.
- `run-tracking`: what every ingestion run and item records (timing, throughput, progress, attempts) and how stuck or slow runs are detected.

### Modified Capabilities

(none; `odds-history-capture` keeps the forward snapshots; this change replaces its backfill tasks 4.2/4.3)

## Impact

- Code: `mlb_baseball/connectors/polymarket.py`, `kalshi.py`, `ingest.py` (tracking), `net.py` (shared rate limiter), doctor checks, new migrations (next free number) for raw tables and tracking columns.
- Data: large new `raw.*` volumes (Polymarket trades are billions of rows on-chain; the plan sizes it first and loads only what the research use needs, recent first). Production runs are owner-logged in `pipeline-recovery/results.md`.
- Rights: Polymarket and Kalshi market data are public and key-free; each bulk dataset gets a row in `docs/SOURCE_RIGHTS.md` before loading.
- Phase gate: owner-directed 2026-10-05 as part of `full-source-ingestion` Phase 4.5.
