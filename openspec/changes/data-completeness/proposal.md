## Why

The owner wants one trustworthy answer to "what data should we hold, and what do we
hold?" for every source, table, season, date, team and player, and wants every gap
closed or explained. `mlb coverage` (PRs #337-#345) now measures part of that. The
2026-10-07 full report showed what is still open:

- 46 tables have no expectation (23 of 39 MLB API tables), so they are counted, not checked.
- Players are checked only against our own tables, not against the Chadwick register.
- Only "Final" games are expected, so 18 "Completed Early" games and all postponed or
  future games are not tracked against MLB's published schedule.
- Each source's full offering (for example about 190 MLB API endpoints, of which we
  load roughly half) has not been scanned, so an unloaded table is invisible.
- Nothing runs the report on a schedule, alerts on a gap, or repairs one, except the
  MLB game-detail repair added in #345.
- Known real gaps remain (81 linescores 2000-2024, 147 roster players, FanGraphs fielding
  2019, 2 Statcast dates, Negro League labelling).

## What Changes

- Run one owned program of work (`goal.md`) that scans, assesses, repairs, re-checks and
  automates, logging every decision and action in `log.md`.
- Give every raw table an expectation or a written reason it has none.
- Add schedule-aware expectations (published schedule for current and future games,
  "Completed Early" counted) and a Chadwick-based player check.
- Add a nightly coverage run with an alert, and bounded self-repair for gaps that have a
  safe, repeatable fix.
- Keep `docs/sources/` and `docs/RAW_INVENTORY.md` current as results land.

## Capabilities

### New Capabilities
- `data-completeness`: what "complete" means, how it is measured, and how gaps are
  repaired, explained and logged.

### Modified Capabilities

## Impact

- `mlb_baseball/coverage/`, source connectors (repair paths only), a nightly coverage
  step, `scripts/` (new or changed cron entries), `docs/sources/`, and this change's `log.md`.
- Owns, and does not duplicate, `full-source-ingestion` (new endpoints and levels) and
  `negro-league-scope` (labelling). This change links to their tasks instead of copying them.
- Production writes follow the approval rules in `goal.md`.
