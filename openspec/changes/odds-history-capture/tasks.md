## 1. Prerequisites

- [ ] 1.1 Read `kalshi.py.dox.md`, `polymarket.py.dox.md`, `tests/AGENTS.md`; confirm what `mlb_baseball/load.py` offers for upsert-without-delete; record the answer in design.md
- [ ] 1.2 Measure current snapshot row counts per day and per run (read-only SQL) and note them in design.md

## 2. Capture job (tests first)

- [ ] 2.1 Write failing test: two snapshot runs with different prices keep both rows (real PostgreSQL fixture); verify it fails
- [ ] 2.2 Write failing tests with fixed HTTP fixtures: snapshot mode fetches open markets only and makes no catalog calls (both sources)
- [ ] 2.3 Implement `--mode snapshot` for Kalshi and Polymarket until 2.1-2.2 pass
- [ ] 2.4 Write failing test then implement `scripts/mlb_odds_capture.sh` skip-when-locked behaviour (shell test or documented dry run)
- [ ] 2.5 Zero-open-markets test: run succeeds, tables exist, zero rows

## 3. Catalog retention (tests first)

- [ ] 3.1 Write failing test: a market absent from the second pull is still in the table with unchanged `last_seen_at`; changed values update the row
- [ ] 3.2 Implement keep-and-stamp for the Kalshi and Polymarket catalog tables (migration if a column is added); verify 3.1 passes and `conform` tests still pass
- [ ] 3.3 Update `.dox.md` files (replace semantics are gone) and `docs/DECISIONS.md` with a new ADR

## 4. Backfill

- [ ] 4.1 Run existing backfill tests; add failing tests for interrupted-resume and no-trade-candle-as-NULL if missing
- [ ] 4.2 Owner approval (plain words): run Polymarket backfill on production; log result in `pipeline-recovery/results.md`
- [ ] 4.3 Owner approval: run Kalshi backfill on production; log result; verify row counts against source for 3 sample markets

## 5. Health and schedule

- [ ] 5.1 Write failing tests then fix doctor: "backfill not run" state replaces missing-table failure; add snapshot-gap check
- [ ] 5.2 Owner approval: install the cron entry; verify snapshots land every interval for one day and the gap check passes
- [ ] 5.3 After one week, review row volume and `meta.ingestion_run` noise; decide retention in a follow-up

## 6. Close out

- [ ] 6.1 `openspec validate odds-history-capture --strict` passes; ruff/type/SQL checks pass; PR merged and change archived
