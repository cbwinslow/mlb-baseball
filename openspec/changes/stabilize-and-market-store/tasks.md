# Tasks

Production `mlb` writes (anything except read-only queries) need owner approval at the step; every such step gets a `changelog/` entry. Never run the local pytest DB suite while a long ingest is running (use CI).

## 1. Stabilize the nightly run

- [ ] 1.1 Choose and configure an alert channel (ask owner); verify by forcing a failing step in a dry run and seeing the notification arrive.
- [ ] 1.2 Add an external "finished" signal and a missing-signal alert; verify by killing a test run partway and receiving the alert.
- [x] 1.3 Split exit code from data-health: nightly rc reflects steps only; add a daily health digest; verify with a test where coverage reports a gap but rc=0.
- [ ] 1.4 Move coverage and repair to a weekly job reading statistics or the ledger; verify the weekly run does no `count(*)` on the market tables (check `pg_stat_statements`).
- [x] 1.5 Add content-hash / Last-Modified skip to the Retrosheet loader; run-twice test proves the second run writes nothing.
- [ ] 1.6 Limit the 5-minute `mlb_api` tick to live games and today's schedule; move transactions/roster/draft to hourly with a skip-if-unchanged hash; run-twice test; confirm WAL rate drop with `pg_stat_wal` over 3 days.
- [ ] 1.7 Update `.dox.md` sidecars for touched connectors and `nightly.py`; add a `changelog/` entry.
- [ ] 1.8 Exit check: 7 nights with rc=0 or a real alert, nightly under 2 h, WAL/day down at least 40%.

## 2. Market price store

- [ ] 2.1 Inventory every reader of `raw.polymarket_price`, `raw.kalshi_candle` (views, SQL files, Python); verify with `pg_depend` and a repo search, recorded in this change.
- [x] 2.2 Scratch-database Timescale test (owner approved): load the 924k-row sample, hypertable with 1-month chunks, compress, read `hypertable_compression_stats`, time a per-token range query; record numbers in `results.md`.
- [x] 2.3 Decision gate: compare 2.2 against the 10 GB target; if missed, stop and take the choice to the owner (more Timescale tuning vs ClickHouse).
- [ ] 2.4 Bad-value discovery per month chunk (regex checks) on production, read-only; record counts in `results.md`.
- [ ] 2.5 Migration for the typed hypertables `_new`, reject tables, and unique keys; test on a disposable DB.
- [ ] 2.6 Chunked copy with immediate compression, throttled; verify per-token per-month row counts and price sums against the old table.
- [ ] 2.7 Rewrite the Polymarket and Kalshi loaders (staging then cast then `ON CONFLICT DO NOTHING`; Polymarket via `dlt`, parity-checked against the old loader on one token range); run-twice idempotency test, bootstrap path, and `doctor` check.
- [ ] 2.8 Pause the backfill, catch up late rows, swap with two renames in one transaction, resume.
- [ ] 2.9 Exit check: the two tables total 10 GB or less, readers unchanged and passing, loader run-twice test green.
- [ ] 2.10 After 7 days and owner approval, drop `_old`; remove the delete-range loader path and now-unneeded casts.
- [ ] 2.11 Retype the snapshot tables the same way if 2.9 passed (separate owner approval).

## 3. Decisions and docs

- [ ] 3.1 Write the ADRs drafted in `design.md` into `docs/DECISIONS.md` after owner approval, and cite their numbers in `design.md`.
- [ ] 3.2 Update `docs/SOURCE_RIGHTS.md` / data-source docs only if the rights profile or table layout description changed.
- [ ] 3.3 Fold in or archive the superseded open changes listed in the review (pipeline-recovery, pipeline-freshness, odds-history-capture, odds-bulk-history) one at a time, each with owner approval.
