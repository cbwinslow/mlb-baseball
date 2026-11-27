# Tasks

Production `mlb` writes (anything except read-only queries) need owner approval at the step; every such step gets a `changelog/` entry. Never run the local pytest DB suite while a long ingest is running (use CI).

Each task is tagged: **[auto]** the agent can finish and test it alone; **[owner]** needs an owner decision, credential or approval first; **[measure]** code is done, proof needs elapsed time on production. A goal-seek run works only the **[auto]** tasks and stops at the first other tag.

## 0. Setup

- [x] 0.1 [auto] Work moved to branch `stabilize-market-clean` (worktree `../mlb-stabilize`, cut from `origin/main`); conflicts with ADR-303 resolved by keeping main's `repair --apply` + `coverage --light`. Pushing and the PR are **[owner]**.

## 1. Stabilize the nightly run

- [ ] 1.1 [owner] Create `~/.mlb/alert.env`; then send one test message and force a failing step to see it arrive.
- [ ] 1.2 [owner] Code and tests done; add the `mlb nightly --check` cron line (only after merge to `main`) and run a forced dead-run test.
- [x] 1.3 Split exit code from data-health; daily digest.
- [ ] 1.4 [measure] Coverage/repair weekly (Monday gate) and row estimate for market tables are coded; confirm with `pg_stat_statements` after a real Monday run that no `count(*)` hit the market tables.
- [x] 1.5 Retrosheet unchanged-archive skip with run-twice test.
- [x] 1.6 [auto] The 5-minute `mlb_api` tick loads only yesterday's and today's schedule, live games and game detail; season schedule, standings, roster, transactions and draft run hourly with a hash skip. Unit tests plus the 53 `test_mlb_api_load.py` integration tests pass on a disposable database.
- [ ] 1.6m [measure] After deploy, `pg_stat_wal` over 3 days shows the write rate down.
- [x] 1.7 [auto] Doc pass done: sidecars (`mlb_api`, `retrosheet_event`, `cli`), ARCHITECTURE nightly paragraph and changelog match the code.
- [ ] 1.8 [measure] Exit check: 7 nights with rc=0 or a real alert, nightly under 2 h, WAL/day down at least 40%.

## 2. Market price store

- [x] 2.1 [auto] Reader inventory done; recorded in `results.md` (no database object depends on either table; only the two connectors, coverage, repair and their tests name them).
- [x] 2.2 Scratch-database Timescale test (see `results.md`).
- [x] 2.3 Decision gate: passed provisionally; re-check after the first production month.
- [ ] 2.4 [owner] Bad-value discovery per month chunk on production (read-only queries; approval because of load on spinning disks); counts into `results.md`.
- [x] 2.5 [auto] Migration 0117 (`meta.create_market_tables`, reject tables) with 8 disposable-database tests incl. compression and duplicate-after-compress; 0116 now creates `timescaledb` before `pg_duckdb`. Production `_new` tables are created in 2.6.
- [ ] 2.6 [owner] Chunked, throttled copy with immediate compression on production; verify per-token per-month counts and price sums. Re-check size target on the first month.
- [x] 2.7 [auto] Storage side of the loader rewrite: `market_store.append_rows` (stage, check, cast, `ON CONFLICT DO NOTHING`, rejects kept), both backfill loaders append through it, `ensure_store` bootstrap path, `doctor` reject check; run-twice and reject tests pass on a disposable database. Not deployed (production keeps the text tables until 2.8).
- [x] 2.7d `dlt` pilot: superseded by the owner decision (2026-10-13) to use `dlt` across ingestion. Moved to `openspec/changes/dlt-ingestion-layer` (task 3.1 and the gate in 1.2-1.5). This change keeps the typed tables and `market_store`, which that change builds on.
- [ ] 2.8 [owner] Pause backfills (`odds-bulk-history`, `odds-history-capture` stay paused), catch up late rows, swap with two renames in one transaction, resume.
- [ ] 2.9 [measure] Exit check: the two tables total 10 GB or less, readers unchanged and passing, loader run-twice test green.
- [ ] 2.10 [owner] After 7 days and approval, drop `_old`; remove the delete-range loader path and now-unneeded casts.
- [ ] 2.11 [owner] Retype the snapshot tables the same way if 2.9 passed.

## 3. Decisions and docs

- [ ] 3.1 [owner] Write the ADRs drafted in `design.md` into `docs/DECISIONS.md` after approval; cite numbers in `design.md`.
- [ ] 3.2 [auto] Update `docs/SOURCE_RIGHTS.md` / data-source docs only if the rights profile or table layout description changed.
- [ ] 3.3 [owner] Fold in or archive the superseded open changes (pipeline-recovery, pipeline-freshness, odds-history-capture, odds-bulk-history, job-retries-alerts) one at a time.
