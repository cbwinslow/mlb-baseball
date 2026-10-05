## 1. Verify and size (read-only)

- [ ] 1.1 Probe live and record in `design.md`: batch endpoint max tokens, window, error shape, throttling headers; Kalshi historical series coverage per baseball series (first date, count), candlestick and trades limits; Polymarket data-api trades limits. Verify numbers are written, none provisional
- [ ] 1.2 Read licences and terms for Becker and SII datasets and the two APIs; add rows to `docs/SOURCE_RIGHTS.md`; verify `scripts/check_dox.py` passes
- [ ] 1.3 Size each load (rows, disk, hours) from 1.1; record the plan in `design.md`

## 2. Run tracking (needed first so everything after is measurable)

Built as database objects (migration 0111, ADR-295) plus `mlb_baseball/opsmon.py`.

- [x] 2.1 Migration: `meta.ingestion_run` columns `items_planned`, `items_done`, `requests`, `last_progress_at`; `meta.ingestion_item.duration_ms`; verify migration test
- [x] 2.2 Progress helper in `ingest.py` (bounded to once a minute) with failing test first; verify with a real PostgreSQL test
- [x] 2.3 Doctor check for a reporting run that went quiet (done: `silent ingestion runs`); a throughput floor per source waits for a measured baseline (task 3.5 records it); verify a seeded stuck run fails with run id and last progress in the message
- [ ] 2.4 Decide on `pg_profile` / `pg_wait_sampling` only after a measured question (record the question and numbers, or record "not needed")

## 3. Polymarket

- [x] 3.1 Shared rate limiter in `net.py` (documented limits as config); failing test: never exceeds the configured rate under N workers
- [x] 3.2 Batch window fetch, newest-first ordering, ledger item per market-window (D3), single writer; failing tests with a fake CLOB that mirrors real behaviour (empty for `interval=max`, windows capped, 20-token cap)
- [ ] 3.3 Gamma markets/events: confirm every field is kept; add what the docs list and we drop; per-trade history from the data API within its limits
- [x] 3.4 Lock: the backfill keeps the shared workflow lock (it finishes in about an hour now); `mlb build` waits for it
- [ ] 3.5 Owner-approved production run (newest first), progress watched in the run row; log counts and timings in `pipeline-recovery/results.md`; verify three sample markets against the live API

## 4. Kalshi

- [x] 4.1 Cutoff-aware market catalog (live + historical, dedupe by ticker); failing test with a fake API that has a cutoff
- [x] 4.2 Series discovery for all baseball series (already dynamic via `GET /series?category=Sports&tags=Baseball`; the connector's existing exclusion list keeps non-MLB leagues out)
- [x] 4.3a Candlesticks per market from the right endpoint; ledger item per market; paced at 16 req/s (documented 20)
- [ ] 4.3b Trades per market (`/historical/trades`, `/markets/trades`): probe volume first, then ledger per market
- [ ] 4.4 Owner-approved production run, newest first; verify against three sample markets; log results

## 5. Bulk datasets

- [ ] 5.1 If rights pass: download Becker (36 GiB) and the SII markets table with checksums into `downloads/`; load into separate `raw` tables with provenance
- [ ] 5.2 Overlap report: markets and price points present in official endpoints versus bulk; record differences in `docs/sources/`
- [ ] 5.3 Decide which bulk tables (if any) stay; the rest are dropped with the reason recorded

## 6. Close-out

- [ ] 6.1 Update `polymarket.py.dox.md`, `kalshi.py.dox.md`, `docs/DATA_SOURCES.md`, `docs/RAW_INVENTORY.md`; supersede `odds-history-capture` tasks 4.2/4.3
- [ ] 6.2 `openspec validate odds-bulk-history` passes; archive after owner review
