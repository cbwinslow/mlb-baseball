Progress is tracked here; reasons and results are in `log.md`. Tick a box only with evidence.

## 0. Already done (for the record)

- [x] 0.1 `mlb coverage` with flags, dates, referenced-id check, live schedule probe (#337, #339, #341, #342)
- [x] 0.2 `docs/sources/` pages for 10 sources (#338)
- [x] 0.3 Raw profile table and data dates (migrations 0112, 0113)
- [x] 0.4 Missing download manifest reported, not silent (#344)
- [x] 0.5 MLB game-detail repair in update and `--mode backfill` (#345); 290 games of 2026 repaired in production, verified by `mlb coverage`

## 1. Scan offerings and measure (read-only)

- [ ] 1.1 Per source, record what it offers vs what the connector loads in `docs/sources/<source>.md`; verify each page names its evidence and date
- [x] 1.2 (the 10 mlb_api season tables now have expectations; attendance stays per-team, no expectation) Give every one of the 46 raw tables without an expectation an expectation or a written reason; verify `mlb coverage` lists none silently and a test fails on an unregistered table
- [x] 1.3 Schedule-aware expectations: count "Completed Early", track Postponed/Scheduled against MLB's published schedule, include the next season when published; verify with a fixture and live probe (PR for branch `feat/schedule-aware-coverage`)
- [x] 1.4 Chadwick-based player check: players seen in rosters, box scores and Statcast exist in the register; verify counts and list unmatched (report line on `raw.register_people`; FanGraphs, Retrosheet, bref ids not checked there)
- [ ] 1.5 Live checks for the other sources (`full-source-ingestion` 0.13): Retrosheet file list, FanGraphs/Baseball-Reference seasons, Lahman release year, Statcast per-day pitch counts (done as a per-game check, PR `feat/statcast-per-game`)
- [x] 1.6 Full report saved to this folder as `results-baseline.md` with every gap classified: repair, scope, unavailable, or open question

## 2. Repair (production writes need approval each time)

- [ ] 2.1 81 old MLB linescores (2000-2024)
- [x] 2.2 (147 -> 1) 147 roster players missing from `raw.mlb_person` (widening is `full-source-ingestion` 0.14)
- [x] 2.3 FanGraphs fielding 2019
- [ ] 2.4 Statcast: 4 games of 2026-10-05/06 (heals with `mlb ingest statcast --mode update`; the 2008-10-29 "missing date" was a false alarm, see log)
- [ ] 2.5 Kalshi (744) and Polymarket (3,560) 2026 items
- [ ] 2.6 Other gaps found in 1.6, one task each
- [x] 2.8 (2024 stats remain; heals after PR 364) MLB reference and stat seasons missing: 2006, 2017-2025 for player pool, coaches, alumni, game pace, free agents, player/team stats and leaders (found 2026-10-07; source serves them; `mlb ingest mlb_api --mode bootstrap` fills them and the old linescores)
- [x] 2.6 (venues: false gap fixed; team ids: accepted, see log) Other gaps found in 1.6, one task each
- [ ] 2.7 After each repair: re-run coverage, record before/after in `log.md`

## 3. Make it permanent

- [ ] 3.1 Bootstrap-from-empty test that every repair path is reproduced. Audit 2026-10-07 (corrected): every raw table maps to a registered connector, `mlb bootstrap` runs all 18, every coverage fix command is a real ingest, and all 18 connectors have an integration load test against a real database (reload-replaces tests included). Not yet proven: one end-to-end run of `mlb bootstrap` on an empty database, which would take days (Statcast, MLB per-game); decide whether to do it in stages on a scratch database.
- [x] 3.2 Nightly coverage step with alert on any new gap (needs a machine-readable list of accepted gaps so a known scope gap does not alert every night); verify with a failing and a passing fixture
- [ ] 3.3 Bounded self-repair for safe gaps beyond MLB game detail (each with a test)
- [x] 3.4 (the check is a nightly step, so the existing `mlb_daily_update.sh` cron runs it; no new cron) Cron entry in `scripts/` (flock, log) and docs in `docs/ARCHITECTURE.md` "Scheduling"
- [ ] 3.5 Update `docs/sources/`, `docs/RAW_INVENTORY.md`, `mlb_baseball/coverage/AGENTS.md`

## 4. Close out

- [ ] 4.1 `mlb coverage` shows zero unexplained gaps; bootstrap-from-empty matches; evidence in `results-final.md`
- [ ] 4.2 `openspec validate data-completeness`; archive the change
