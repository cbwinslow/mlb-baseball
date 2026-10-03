## 0. Rules for every production step

- [x] 0.1 Create `results.md` with an approval log table (step id, exact command, target database name, who ran it, time, output captured, backup id in force); verify every production write below adds a row before and after it runs
- [ ] 0.2 Decide where `mlb nightly` (migrations 0108/0109, `nightly.py`) lives: it is only on branch `plan/stable-ids-and-job-retries`; verify `results.md` records whether it is merged first or this change is built on that branch

## 1. Phase 1: confirm the real state (read-only)

- [x] 1.1 Re-run `mlb doctor` against production `mlb`, save full output to `results.md`, and record the database name and the free disk (`df`) at that moment; verify all failures are listed with exact text (27 at the start; the count may now differ)
- [x] 1.2 Confirm the 14:23 UTC 2026-10-02 run was an interrupted manual test: read `meta.ingestion_run` ids 17254-17264, `pg_stat_activity`, and `logs/mlb_daily_update.log` around 14:23-14:27; verify `results.md` states cause and evidence
- [x] 1.3 Check the four stuck sources (statcast, kalshi, polymarket, retrosheet_box) for partial raw writes: compare per-source max load timestamp and duplicate natural keys against the 06:00 run; verify the result is written down; if partial rows exist, record an issue and do not edit raw
- [x] 1.4 Re-check live lock and session state: advisory locks in `pg_locks` joined to `pg_stat_activity`, and sessions `idle in transaction`; verify the result (on 2026-10-03 no advisory lock was held and no idle-in-transaction session existed, so the "workflow lock" failure may already have cleared) is saved before any repair
- [ ] 1.5 Classify every doctor failure as real defect / wrong check / accepted, using a sample of the offending rows as evidence (not the check's own logic); verify a table in `results.md` has one row per failure (N of N classified), each with a review date and, for "wrong check" or "accepted", the owner's sign-off

## 2. Phase 1: safety first (production `mlb`, owner-approved, one command at a time)

- [ ] 2.1 Size the backup before taking it: `pg_database_size` by schema, current free disk, and what `mlb backup` writes (plain-SQL, whole database; `--schema` scopes it but scoped dumps are not recorded for the doctor freshness check, `backup.py:88-95`); record the chosen scope and a free-space rule (free disk after the dump and a restore must stay at least 20 GB) in `results.md`
- [ ] 2.2 Confirm the backup and the 06:00 cron job cannot overlap (`scripts/mlb_backup.sh` flock, cron schedule); verify the schedule gap or lock is written down. Take the backup with a `lock_timeout` and idle-in-transaction timeout so it cannot queue behind or block a rebuild
- [ ] 2.3 Add a small restore-check script that restores into an explicitly named disposable database (never `mlb`; the script refuses any target named `mlb`), then compares row counts for all schemas, indexes, constraints and sequences, and runs `mlb doctor` against it; verify with a test on a tiny database that it fails on a seeded difference and refuses the production name
- [ ] 2.4 Take the first full `mlb backup` of `mlb`, run the restore check, then drop the disposable database; verify zero restore errors, all counts match, and `results.md` records a pass. No later production write starts without this recorded pass
- [ ] 2.5 Pause the 06:00 cron entry, then run the stale-run repair (dry run or an equivalent read-only listing first; save it); note `mlb repair-runs` only marks dead-pid `running` rows failed (`ingest.py:264-301`) and does not touch locks. Verify no `running` rows remain and the rows reaped are exactly those listed. Re-enable cron only after step 2.7
- [ ] 2.6 List pending migrations (doctor's migrations check) and read each for lock level, rewrites and reversibility (0108, 0109 at least); verify `results.md` lists them. Take a fresh backup immediately before applying; apply with a `lock_timeout`; verify `mlb doctor` migrations check passes
- [ ] 2.7 Run `mlb catalog build`; verify `meta.metric` row count equals a direct count of `mlb_baseball/metrics/*.yaml` entries, keys are unique and non-null, and a second run leaves the table unchanged (idempotent)
- [ ] 2.8 One-off `VACUUM (ANALYZE)` on `raw.mlb_win_prob`, `raw.fangraphs_fielding`, `raw.mlb_linescore`, `raw.mlb_game_context`, run by the owner outside the nightly window; verify `pg_stat_user_tables` shows `last_vacuum`/`last_analyze` set and the doctor never-vacuumed check passes. Also record dead tuples and autovacuum settings for the 23 rebuilt tables and `age(datfrozenxid)`

## 3. Phase 1: correct the health checks

- [ ] 3.1 Read `mlb_baseball/connectors/*.dox.md`, then change the polymarket price and kalshi candle checks (in `connectors/polymarket.py` and the kalshi connector, called through `health_check()`; not `doctor.py`) so an absent backfill table is informational, but an existing table that is empty, partial or stale still fails; verify connector tests cover absent / empty / partial / healthy, and a missing `raw.*_snapshot` table still fails
- [ ] 3.2 Make `mlb doctor` report a crashing check (for example the `feat` binder error on `home_pa_30d`) as ERROR, distinct from pass and fail, counted in the totals; verify a test where a check raises shows ERROR and is never read as a pass
- [ ] 3.3 For each remaining wrong check found in 1.5, add one task here (written when found) with a test that fails on a seeded defect and passes on healthy data; verify each uses the repository's disposable PostgreSQL fixtures
- [ ] 3.5 Fix the 2026 postseason leak at its cause: derive each season's regular-season end date in `connectors/bref.py` from `core.game` (last `regular` game date) instead of the hardcoded `_REGULAR_SEASON_END` list, so a new season never needs a manual entry; verify with a test where a season has regular and `wildcard` games and the window stops at the last regular date, and a test for a season still in progress. Then (owner-run, after backup) re-ingest `raw.bref_*` for 2026 and rebuild `gold.player_season` / `gold.team_season`; verify the doctor envelope check passes and Albies 2026 shows 162 games
- [ ] 3.4 Re-run `mlb doctor`; verify the only failures left are real defects from 1.5, each with a tracked issue or fix task, and the count equals the table in `results.md`

## 4. Phase 2: measure before changing

- [ ] 4.1 Prepare measurement: confirm `pg_stat_statements` is loaded, reset it before the measured night, set `log_lock_waits=on` and `deadlock_timeout=1s` for the run, and sample `pg_stat_activity` (wait event, `xact_start`) every 30 s during conform; verify each setting is shown by `SHOW` / a query and recorded
- [ ] 4.2 Record per-source `update`, per-step `conform`, per-relation `report` and per-step `predict` timings for one full production night in `results.md`; verify the table sums to within 5% of the logged phase totals, and the top-N queries by `total_exec_time` are listed
- [ ] 4.3 Record lock waits and which readers were blocked during conform; verify the longest wait per table is stated
- [ ] 4.4 Replace the provisional targets in `design.md` with measured baselines and numeric acceptance values (total nightly time, conform+report time, longest lock wait on a read-served table); verify no number there is still labelled provisional and the lock threshold used by 8.2 is defined

## 5. Phase 2: store timings in the database (the spec requires it)

- [ ] 5.1 Add a numbered migration and code so every run records per-phase, per-step elapsed seconds in a `meta` table (run id, phase, step, seconds), from `timing.py`'s existing measurements, for cron runs as well as `mlb nightly`; verify a PostgreSQL integration test that a run leaves the rows and that last night's timings are queryable by SQL alone
- [ ] 5.2 Add a doctor check that shows last run's total and flags a phase more than 50% over its trailing median; verify with seeded rows

## 6. Phase 2: fix the spec gaps in `stable-ids-incremental-conform`

- [ ] 6.1 Edit that change so `core.game` is upserted and never delete-reinserted by season, and state explicitly whether `core.market` stays delete-by-season (`design.md` D2 and D4, `tasks.md` 5.1); verify `openspec validate stable-ids-incremental-conform` passes and no artifact contradicts D2 for any table
- [ ] 6.2 Strengthen the fingerprint (per-season content checksum, code version, reference-data version) and make pending dirty seasons persist across failures; add a periodic full-rebuild guard (for example weekly) and a doctor check that compares fingerprints; verify the spec has a scenario where a value changes with the same row count and key set
- [ ] 6.3 Change that change's equivalence task so it compares all non-key columns of `core` and `gold`, with a separate id-stability test; verify the task text names both and both layers
- [ ] 6.4 Add lock rules to that change's design: build into staging first, publish in a short transaction with `SET LOCAL lock_timeout`, use `DETACH PARTITION ... CONCURRENTLY` outside a transaction block with retry, add a validated CHECK before `ATTACH`, and run `ANALYZE` after each bulk load; verify each rule appears in the design and has a test or measured check
- [ ] 6.5 Document the foreign-key graph that the 23-table truncate depends on (including references by table identity); verify the graph is in `design.md` and every table in the truncate list appears in it

## 7. Phase 2: implement and prove

- [ ] 7.1 Execute `stable-ids-incremental-conform` under its own task list; verify each of its tasks is ticked with its own verification and the equivalence test passes in CI
- [ ] 7.2 Production comparison, read-only against production: incremental result versus a full rebuild into a named disposable database, size-checked first against free disk (the plan must not need a copy of raw; run the comparison on `core` and `gold` outputs only); verify every difference is listed and explained in `results.md`
- [ ] 7.3 Take a fresh verified backup, add an off switch (a flag or setting that forces full mode) and an automatic fallback to full mode if dirty-season detection errors; verify the switch with a test. Then switch `scripts/mlb_daily_update.sh` to incremental mode
- [ ] 7.4 Observe three nightly runs after the switch; verify no stale runs, `mlb doctor` shows only accepted failures from 1.5, and the measured total and conform+report time meet the numeric values set in 4.4

## 8. Close-out

- [ ] 8.1 Record the single-approach decision as an ADR in `docs/DECISIONS.md` (why A, why not B or C) and update `openspec/project.md` NOW/NEXT and `openspec/HANDOFF.md`; verify `scripts/check_dox.py` passes
- [ ] 8.2 Decide on the short-swap fallback (option B) only if 4.3 and 7.4 show lock time still above the 4.4 threshold; verify the decision and its numbers are written in `results.md`, or "not needed" is recorded
- [ ] 8.3 Add doctor monitoring for disk free, backup age and size, dead tuples, `age(datfrozenxid)`, longest transaction age; verify each shows in `mlb doctor` output
- [ ] 8.4 Archive with `/opsx:archive` after owner review; verify `openspec validate pipeline-recovery` passes first
