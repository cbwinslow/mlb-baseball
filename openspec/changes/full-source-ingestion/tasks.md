## 0. Foundations (no production writes)

- [x] 0.1 Record the owner's 2026-10-05 direction in `openspec/project.md` NOW/NEXT (full-source ingestion, pro first, no paid providers) and state that it must not delay `pipeline-recovery` close-out; verify `scripts/check_dox.py` passes
- [ ] 0.2 (generator verified 2026-10-05: `mlb inventory --markdown` against production differs from the committed file only by live row counts and the new `kalshi_candle`; file regenerated in the coverage PR; PR merges still owner-controlled) Merge PR #310 (audit) and #311 (generated inventory); verify `docs/RAW_INVENTORY.md` regenerates identically with `mlb inventory --markdown`
- [ ] 0.3 Verify the origin and terms of `mlb-statsapi-spec.json` (where MLB publishes it, licence text); record in `docs/SOURCE_RIGHTS.md`; only then copy it under `docs/sources/mlb_api/`; verify the file's header and URL are cited
- [ ] 0.4 Read the full MLB Terms of Use and record exact wording on automated collection, rate, and retention in `docs/SOURCE_RIGHTS.md`; verify the owner signs off the `local_research` risk statement for the new phases
- [x] 0.5 (done 2026-10-05, evidence in `pipeline-recovery/results.md`: laptop has the saved responses, 946/946 checksums verified, copied to `downloads/mlb_api/`) Compare the `cbwlap1` database (PostgreSQL 17, port 5433): list its tables and row counts read-only, dump only the win-probability/context/schedule tables, rsync to this host, load into a named scratch database, and compare keys/counts/values with `raw.mlb_win_prob`/`raw.mlb_game_context`; verify results and whether source JSON exists there are written in `pipeline-recovery/results.md`
- [ ] 0.6 Measure one saved MLB feed season (about 2,430 games) for disk size, request time and parse time; set the Phase 2 disk budget, concurrency and rate; verify numbers are recorded in `design.md` D4 and no number stays provisional
- [ ] 0.7 Write the shared helper for the pattern in D1 only if three phases need the same code (per-season artifact + ledger + replay); otherwise reuse `analytics` functions directly; verify with a real PostgreSQL test that load, replay without network and checksum-mismatch failure all behave per the spec
- [ ] 0.8 Create `docs/sources/` with one page per existing source (MLB Stats API, Retrosheet, Lahman, Statcast, FanGraphs, Baseball-Reference, Chadwick Register, Kalshi, Polymarket, news): offers vs stored vs reason for each gap, from `docs/SOURCE_COVERAGE_AUDIT.md` and `docs/RAW_INVENTORY.md`; verify every raw table appears on exactly one page and `scripts/check_dox.py` (or a new docs check) fails on an orphan table — IN PROGRESS: `docs/sources/` created; `mlb_api.md` done, one page per remaining source to follow
- [ ] 0.9 Record an ADR superseding the "skip because redundant" parts of ADR-017/018/019; verify it is in `docs/DECISIONS.md`

- [x] 0.10 (done 2026-10-05: `mlb coverage` in `mlb_baseball/coverage/`, tests `tests/integration/test_coverage.py`; read-only run on production lists per-source gaps, e.g. mlb_api 2026: 289 final games without win probability/context; started with the MLB API as planned) Coverage finder `mlb coverage`: per source, ask the source what exists (MLB API: games per season from `raw.mlb_schedule` x each per-game dataset; Retrosheet: published file list; Statcast: dates; FanGraphs/BBRef: seasons) and compare with what each raw table holds; print what is missing and the exact `mlb ingest ...` command that fixes it. Reuse `mlb status --season-coverage`, `source-check`, `meta.ingestion_item` and the doctor coverage checks; start with the MLB API; verify a test with a seeded gap lists it and the fix command closes it
- [ ] 0.11 Save-first rule: NEW datasets use the save-the-response pattern (D1). Existing working connectors (Statcast, FanGraphs, Baseball-Reference, register, Kalshi/Polymarket, news) are NOT changed unless a measured problem appears; record the reason per connector in its source page

## 1. MLB Stats API: cheap per-season endpoints (hundreds of calls)

- [ ] 1.1 Probe and record first-valid year, request count and response shape for: schedule hydrates (weather, officials, decisions, broadcasts, seriesStatus, team, venue), stat groups fielding/catching/running, stat types sabermetrics and statSplits, `highLow`, `meta` enums, `draft/prospects`, postseason series, milestones, award recipients, transactions (all types incl. trades); verify the table is in the MLB source page
- [ ] 1.2 Migration for the new raw tables (one per dataset, naming per D8); verify migration test and `mlb inventory` list them
- [ ] 1.3 For each dataset: failing test first (fixture response saved as artifact, replay from it, 404 as `unavailable`, rerun idempotent), then the loader using the D1 pattern; verify tests use real PostgreSQL
- [ ] 1.4 Add `mlb ingest mlb_api --stage <name>` entries and bootstrap wiring so a normal `mlb bootstrap` includes them; verify `mlb preflight` lists the planned commands
- [ ] 1.5 Doctor/ledger coverage per dataset; verify a seeded gap fails the check
- [ ] 1.6 Owner-approved production run, one stage at a time, logged in `pipeline-recovery/results.md`; verify raw counts against the probe expectations and regenerate `docs/RAW_INVENTORY.md`

## 2. MLB Stats API: per-game feed (GUMBO), pro years first

- [ ] 2.1 Probe pitchData/hitData/playEvents population by year (1950-2007 shell check; 2008+, 2015+, 2020+, 2025 field changes); record the per-year field table in the MLB source page; decide the backfill start year (D3)
- [ ] 2.2 Design the parsed tables from the feed (plays, pitch events, hit data, runners, fielding credits, officials, weather, decisions, boxscore lines, linescore) against the OpenAPI spec; verify each field either has a column or is documented as kept only in the saved artifact
- [ ] 2.3 Migration + failing tests with a saved real feed fixture from three eras; loader fetches once per game, saves NDJSON batch artifacts, writes ledger rows, parses all tables from the artifact; verify replay without network gives identical tables
- [ ] 2.4 Resumable season stage with workers and rate limit (`--stage feed`, `--start-year/--end-year`); verify interrupted-run test
- [ ] 2.5 Owner-approved production run, newest seasons first, then back to the decided start year; log each season's counts; verify ledger coverage 100% terminal per season and doctor passes
- [ ] 2.6 Parity evidence for 2026 against the existing `raw.mlb_playbyplay`/`raw.mlb_boxscore_*`; decide in the ADR whether the old writers stay (no permanent dual writers within one table family)

## 3. Win-probability and context responses saved (closes `pipeline-recovery` 9.5)

- [ ] 3.1 Source JSON was found on `cbwlap1` and copied (0.5): add and test a ledger-seeding step that reads `downloads/mlb_api/manifest.json` and the NDJSON artifacts, writes `meta.ingestion_item` rows (`loaded`/`unavailable` with path, sha256, rows), and checks each game's row count against production raw; owner-approved production run; then fetch only the ~444 games not in the artifacts. Fallback only if the artifacts prove unusable: run the existing `--stage analytics` backfill (owner chooses years), newest first
- [ ] 3.2 Verify `mlb_api analytics durable coverage` passes (1950s source gaps recorded as `unavailable`) and update `pipeline-recovery` tasks 9.5

## 4. Other free pro sources: completeness and gaps

- [ ] 4.1 Retrosheet: explain box-score coverage (18k of 211k games) against what Retrosheet publishes; ingest what is missing; verify per-year counts versus the published file list
- [ ] 4.2 Statcast: per-year coverage table (2008+ pitch, 2015+ tracking, bat tracking, leaderboards) with gaps filled; Chadwick register and Lahman release currency; FanGraphs unbuilt boards and Baseball-Reference season lines/other products allowed by rights; each with a rights row first
- [ ] 4.3 Trades/transactions: MLB API transactions 2000+ (task 1.x) plus any lawful free history before 2000 (Retrosheet transactions are frozen at 2021); record sources and rights
- [ ] 4.4 Weather and umpire data: schedule/feed weather and officials (Phases 1-2), Retrosheet umpires; research any additional free source and record its rights before use
- [ ] 4.5 Odds: finish `odds-history-capture`; research free historical odds sources and their terms; no paid providers
- [ ] 4.6 One source page update and inventory regeneration per source; verify the catalogue check passes

## 5. Minor leagues, independent and college (after all pro phases)

- [ ] 5.1 Schedules, teams, rosters, transactions for sportId 11-14, 16, then winter (17) and independent (23); probe first valid years (about 2005); then the per-game feed for those levels
- [ ] 5.2 College (22) only after owner review of terms and cost
- [ ] 5.3 Rights reviews for Seamheads, KBO, NPB before any ingest; ingest only the sources that pass

## 6. Close-out

- [ ] 6.1 `docs/BOOTSTRAP_RUNBOOK.md`: ordered commands, duration, disk, request counts per stage; verify by running the documented sequence against a fresh disposable database for the cheap stages
- [ ] 6.2 Update `docs/DATA_SOURCES.md`, connector `.dox.md` files, `docs/RAW_INVENTORY.md`; verify `scripts/check_dox.py` passes
- [ ] 6.3 `openspec validate full-source-ingestion` passes; archive with `/opsx:archive` after owner review
