# Handoff — 2026-11-08 (fresh-database-bootstrap)

## Where this change stands

- **1.0 done.** `bootstrap` can take a slice: `--since-year` /
  `MLB_BOOTSTRAP_SINCE_YEAR` / `bootstrap_since_year`, applied to the season loops
  of statcast, statcast_leaderboard, bref, fangraphs, retrosheet,
  retrosheet_gamelog, mlb_api and the era archives of retrosheet_event /
  retrosheet_box. Sources without a season grain load whole. Ported to `main` on
  2026-11-08 (it had been stranded on the unmerged `stabilize-and-market-store`).
- **1.1 done (2026-11-08).** On a brand-new `mlb_fresh_rehearsal_20261108`:
  `preflight --with-conform` OK, `migrate` applied every migration from empty in
  84s.
- **1.2 / 1.3 not done.** The slice bootstrap has not run against that database
  yet; record per-source outcome, rows, requests and time in `design.md`, then
  `coverage` → `conform` → `audit` → `doctor`.

## Traps found so far

- The nightly conform rebuilds `core.play` / `core.pitch` in one transaction
  (~75 min: `build_plays` 2741s + `build_pitches` 1751s) and holds exclusive
  locks on `core.*` the whole time, so any `doctor`/`coverage` run during that
  window blocks rather than fails. Schedule the rehearsal outside 06:00–08:30
  UTC or accept the wait.
- `mlb doctor` must not be judged on wall time alone: it also waits on those
  locks. The table-scan problem (whole-table `count(*)` over the 151 GB market
  tables) is fixed separately in #404.
- Use a dated database name for the rehearsal (`..._20261108`); the older
  `mlb_fresh_rehearsal` holds a partial 3 GB copy and is left untouched.
- Do not run two pytest invocations at once: `tests/conftest.py` builds a shared
  template database and they collide.

## Next

1. 1.2: `mlb bootstrap --since-year 2025 --skip statcast statcast_leaderboard mlb_api`
   on `mlb_fresh_rehearsal_20261108` (the skipped three are the multi-day full
   history loops). Record results in `design.md`.
2. 1.3: `coverage`, `conform`, `audit`, `doctor`; every FAIL gets a task line.
3. 2.x: fix each break at its own layer with a test that starts from an empty
   schema; decide how the price backfills and `raw.mlb_person` join the
   new-user path (2.2).
4. 3.x: one chaining command + fixture-slice proof. 4.x: runbook/changelog.
