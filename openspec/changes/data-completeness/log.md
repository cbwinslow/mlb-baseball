# Decision and action log

Append only, newest at the bottom. Format in `goal.md`.

## 2026-10-07 (UTC)

- **Action:** full `mlb coverage --missing-only --probe` run (read-only). **Result:** gaps listed; 46 raw tables had no expectation. Retrosheet "held 0" lines were a false alarm from a checkout with no `downloads/`; fixed in #344.
- **Action:** `mlb ingest mlb_api --mode update` then `--stage analytics --start-year 2026 --end-year 2026`. **Approval:** owner, "yes go ahead". **Result:** 2026 win probability, linescore and context filled; box score, play-by-play and umpires still missing for 290 games.
- **Decision:** the nightly update only fetched game detail for today's games, so missed days were never repaired. Built the repair into `update` (20 games per run) and `--mode backfill` (all) instead of running a loose script. **Rejected:** one-off script (blocked by the auto-mode classifier, and not reusable). **PR:** #345.
- **Action:** `mlb ingest mlb_api --mode backfill`. **Approval:** owner, "yes go ahead" to the repair. **Result:** all 290 games repaired; `mlb coverage --source mlb_api` shows no box score, play-by-play, umpire, context or win probability gaps for 2026.
- **Decision:** `negro-league-scope` spec extended (API games, mixed games, derived from `raw.retrosheet_team0`, bootstrap test). **PR:** #343.
- **Decision:** start this change (`data-completeness`) as the single driver; it links to `full-source-ingestion` and `negro-league-scope` rather than copying their tasks.
- **Decision:** owner approved `goal.md`, `tasks.md`, `log.md` as written. Standing approvals: none yet.

### Handoff (2026-10-07, before first compaction)

- **Next step:** task 1.1 (per-source offerings vs loaded, read-only), then 1.2 (an expectation or reason for the 46 raw tables without one), then 1.3 (schedule-aware) and 1.4 (Chadwick players).
- **State:** `main` has everything merged through #345. No ingest is running. Kalshi backfill finished 2026-10-06.
- **Running a checkout:** work from a worktree under `~/workspace/` (for example `git worktree add ~/workspace/mlb-<topic> -b <branch> origin/main`); the main checkout is behind. For database access `set -a; . ~/workspace/mlb/.env; set +a`. `downloads/` is not in worktrees: `ln -sfn ~/workspace/mlb/downloads downloads` before `mlb coverage`, and remove the link before committing.
- **Tests:** `uv sync --extra dev`, then `PYTHONNOUSERSITE=1 uv run python -m pytest <file> -q -p no:cacheprovider`. Tests use disposable databases.
- **OpenSpec CLI:** `~/.nvm/versions/node/v24.16.0/bin/openspec` (put that folder on PATH).
- **Reading the earlier detail:** transcript `~/.claude/projects/-home-cbwinslow-workspace-mlb/a6d0ca90-cb21-4107-8068-e73b621adf6b.jsonl`.
- **Open owner decisions:** Negro League labelling goes through `negro-league-scope` (spec updated in #343; task 1.1 there is the measuring). Lahman Negro League data is licensed from Seamheads (rights review pending). Cite Chadwick ODC-By in `SOURCE_RIGHTS.md`. FanGraphs terms wording is second-hand.

## 2026-10-07 (UTC), after compaction

- **Action:** `mlb coverage --missing-only --json` (read-only, from a worktree). **Result:** 17 tables with a gap (list in `results-baseline.md` once written).
- **Finding (wrong expectation, not a gap):** 7 Statcast leaderboards were expected from 2015 but Savant serves them later. **Evidence:** live probe 2026-10-07, same call returns 0 rows the year before and rows the first year (arsenal 2017; catch probability, jump, OAA, directional OAA 2016; spin direction 2020). **Decision:** record the first served year per board in `statcast_leaderboard.FIRST_SERVED_YEAR` and let the report read it. **Rejected:** loosening the report or hiding the tables.
- **Finding (wrong expectation):** `downloads/retrosheet_box/manifest.json` counted 3 lookup files (TEAMABR.TXT, biodata.zip, rosters.zip) as unloaded archives. **Decision:** the connector marks them `reference` and the report skips that status. The existing manifest keeps "downloaded" until the next `retrosheet_box` run.
- **Finding (real gap):** FanGraphs park factors exist at the source for every season 1871–1900 (live probe, 8–33 rows each) but we hold only 1901+. **Cause:** an earlier one-off backfill (`logs/fangraphs_pf_backfill.log`) started at 1901. **Follow-up:** task 2.3 (repair needs owner approval).
- **PR:** branch `fix/coverage-board-first-years`.

- **Decision (task 1.3, schedule-aware):** (a) report counts `Completed Early` games as played (271 since 2004, 18 in 2026, official games with box scores); the repair also covers them. (b) New check `raw.mlb_schedule (past games settled)`: a regular-season or postseason game dated before yesterday and still Scheduled is a gap (before: 0 found). (c) `update` loads next season's schedule once published, at most once a day; MLB already serves 2027 (2,430 games from 2027-03-25) and we held none. (d) `--probe` compares next season when the source lists games. **Evidence:** live probe showed `2027 held 0, source 2,430`; Completed Early expectation adds 4 missing linescores and 1 new 2026 game with no detail (a game played since the repair, to be healed by `update`). **Rejected:** counting Postponed games (they are replayed under a new id, so the old id is not expected to have detail).
- **Follow-up:** 2027 schedule fills on the next nightly `update` after this merges. The 2006 exhibition rows stuck as Scheduled are outside the check (game type E).

- **Action (task 1.4, read-only):** compared every player id the sources use with the Chadwick register (`raw.register_people`, loaded 2026-10-06, 526,894 rows). **Result:** MLB roster 20,210 ids, 29 not in the register (all Negro League players 1922-1945); box scores 2,136 batters and 1,785 pitchers, 5 missing (all in 2026 exhibition games against national teams); Statcast 6,800 batters and 4,948 pitchers, 0 missing; 2026 roster 0 missing. Umpires: 4 not in the register, 2 are placeholder rows ("NO UMPIRE", "1B Umpire"). Retrosheet roster 853 of 24,606 unmatched, all last seen before 1970 (mostly Negro League). FanGraphs 2,576 of 22,608 unmatched; 256 are 2026 debuts the register lists by MLB id but without a FanGraphs id yet.
- **Decision:** add the MLB-id check as a permanent report line on `raw.register_people`; the fix is `mlb ingest register`. Other id systems wait until a use needs them. **Design note for 3.2:** the nightly alert needs a file of accepted gaps (table, count, reason) so these known scope gaps do not alert every night, while any new gap does.

- **Decision (Statcast completeness):** measure `raw.statcast_pitch` per game instead of per date. **Evidence (read-only):** every played regular-season or postseason game from 2008 to 2025 has pitch rows (2008: 2,460 of 2,460 ... 2025: 2,477 of 2,477; 2020: 951 of 951); 2026 lacks 4 games, all from 2026-10-05 and 2026-10-06 (the update has not run since). The old per-date line flagged 2008-10-29: that is World Series game 5, suspended on 2008-10-27 and resumed on 2008-10-29, which Savant files under its start date, so it was a false alarm. **Limit:** a game with only some pitches still counts as held. **Follow-up:** 54 games since 2015 have under 120 pitches (could be shortened games); compare with play-by-play pitch counts for 2026 later. `statcast.update()` reloads the whole current season, so the 4 games heal on the next run (task 2.4, needs approval).

### 2026-10-07 UTC: goal 2, baseline results
- What: wrote `goal-2.md` (PR #351) and `results-baseline.md`; coverage re-run on the updated main checkout.
- Finding: the main checkout had run old code until fast-forwarded today (owner approved: "ok yea"); the nightly now applies migrations 0112/0113.
- Numbers: Kalshi missing 744 -> 1,492 and Polymarket 3,560 -> 5,750 (new 2026 items arrived; backfill not run); Statcast 4 -> 2 games; linescores 85.
- Follow-up: ask owner per repair command, cheapest first.

### 2026-10-07 UTC: tasks 3.2 and 3.4 built (branch feat/accepted-gaps)
- What: `accepted_gaps.toml` (8 scope entries, each with ceiling, reason, owner); `mlb coverage --unexplained`; new nightly step `coverage` (alerts on any gap not accepted).
- Why: a known scope gap must not alert every night, a new or growing gap must. Rejected: a per-table threshold flag (hides growth); a separate cron (the nightly already has flock, log, retries and alerts).
- Note: until the real repairs run, the nightly coverage step will alert (FanGraphs, linescores, 147 people, Kalshi, Polymarket). That is the intended signal.
- Tests: unit (ceilings, never-accept empty/absent), nightly order. Approval: none needed (code on a branch).

### 2026-10-07 UTC: FanGraphs narrow repair built (branch feat/fangraphs-missing-seasons)
- Live probe (read-only): basic park factors serve 1871 (9 rows) to today; handedness serves 2002 on only; leaders `fld` 2019 serves 2,269 rows. So both gaps are real and repairable.
- What: `mlb ingest fangraphs` (bootstrap) now skips past seasons already held for park factors, prospects and splits (as leaderboards already did) and no longer asks the handedness board for years before 2002. A re-run fetches only the missing 2019 fielding and 1871-1900 park factors, plus the current season.
- Why: the old bootstrap re-fetched every park-factor season and all splits (hundreds of calls) to fill two holes. Rejected: a new repair command (same code path twice).
- Tests: rerun fetches only missing units; handedness not asked before 2002.

### 2026-10-07 UTC: task 2.3 repaired (FanGraphs)
- Command: `mlb ingest fangraphs --mode bootstrap` on production. Approval: owner, "yes please go ahead" (named command: add the missing FanGraphs seasons).
- Before: fielding missing 2019; park factors missing 1871-1900 (30 seasons). Fielding rows 181,015.
- After: `mlb coverage --source fangraphs --missing-only` says "nothing to report". Fielding 183,284 rows (+2,269, matching the live probe of 2,269 for 2019). Only the current season was otherwise reloaded.
- Also done today: main checkout fast-forwarded to 52d55eb (owner approved in the same message).
### 2026-10-07 UTC: bootstrap audit (owner request: every table fillable by an idempotent bootstrap)
- Found (read-only): all 150 inventory tables belong to one of 18 registered connectors; `mlb bootstrap` runs every one; coverage fix commands are all real ingest commands. Static evidence only: raw tables are created by the first load, so only a run proves it.
- Gap: 9 connectors have no direct `bootstrap()` test (listed in task 3.1). Deliberate scope gap to raise: mlb_api play-by-play/box score load from 2026 only (ADR-018/019), though the project aim is all history.
- Next: tests per missing connector (branch/PR each); owner decision on the 2026-only play-by-play.

### 2026-10-07 UTC: correction to the bootstrap audit
- The entry above said 9 connectors lacked a bootstrap test. That came from a grep for `<name>.bootstrap(` and was wrong: those connectors are tested through their load functions (`tests/integration/test_<name>_load.py`, 2 to 11 tests each, reload-replaces included). Retracted; task 3.1 text corrected.
- Owner question on MLB play-by-play/box scores: checked read-only. Retrosheet event data holds 208,693 games from 1900 to 2025, so MLB's play-by-play before 2026 is the same plays; 2026 is not in Retrosheet yet, which is why MLB's feed starts there. Retrosheet publishes box scores directly only to 1961 (we hold 1871-1961); later box scores derive from the event data. Not literally identical (MLB adds pitch-level fields; Statcast covers 2008+). Decision stands: no change.
- Open approval: the linescores run (`mlb ingest mlb_api --stage analytics --start-year 2000 --end-year 2024`) awaits an explicit yes naming it.

### 2026-10-07 UTC: false venue gap found and fixed in coverage
- Found (read-only): `mlb coverage` reported 351 venue ids missing. Joining on the numeric value shows 0 missing: schedule stores some ids as `17.0`, venue table as `17`. A wrong expectation, not missing data. Persons (147) and teams (70) stay missing after normalising, so those are real.
- Fix: `Referenced` strips a trailing `.0` before comparing; test added (a real fraction such as `4.5` is kept). Task 2.6 venue part closed. Team ids remain: schedule teams 160 (1934-2027), 159, 6234 look like Negro League and future ids; to classify after the re-count.

### 2026-10-07 UTC: task 2.8 run and root cause found
- Command: `mlb ingest mlb_api --mode bootstrap` on production. Approval: owner, "yes" (named command), plus permission rule added by the owner.
- Result so far: reference block FAILED again for 2018-2026 with a 404 from `teams/<id>/leaders?leaderCategories=era`. One 404 rolls back the whole season's reference data. That is the cause of the 9-10 missing seasons (not a one-off failure).
- Fix: a 404 for one team/season/category is an empty answer (PR fix/reference-404, unit tests). Rerun needed after it merges; approval to be asked again.
### 2026-10-07 UTC: docs/sources/mlb_api.md updated with today's verified facts (task 1.1, MLB part). Other sources' pages still to do.
### 2026-10-07 UTC: task 1.2 probe found a real gap (MLB reference seasons)
- Read-only probe: game pace, coaches, stats and leaders return data for 2006, 2016, 2019, 2024, 2025 and 2026 at the source. We hold 2000-2026 minus 2006, 2017-2023 and 2025 (stats also 2024): 9-10 seasons across 9 tables, all wholesale. Looks like seasons whose reference block failed or never ran (one try/except per season).
- Change: these tables now have a season expectation (from 2000; free agents 2001) with constants `FIRST_REFERENCE_YEAR`/`FIRST_FREE_AGENT_YEAR` and the evidence. Older years are sparse at the source and unprobed.
- Repair (needs approval): `mlb ingest mlb_api --mode bootstrap` fills those seasons, and also the 85 linescores through its analytics step. Cost not yet measured: it also reloads the venue, team, person and draft catalogs after the season loop. Narrower alternative for linescores only: `--stage analytics --start-year 2000 --end-year 2024`.
### 2026-10-07 UTC: team id gap classified (task 2.6)
- Found (read-only): 124 schedule team ids are absent from `raw.mlb_team_history`. 5 are Negro League clubs; 121 are 1949 or later, and all but 8 appear only in spring-training or exhibition games. The 8 are All-Star league sides (ids 159, 160) and 2026 postseason placeholders ("AL Higher Seed", "Lower Seed League Champion"). None is a real club.
- Decision: accept with ceilings (home 90, away 100) in `accepted_gaps.toml`; real clubs missing would exceed or be listed. Rejected: loading minor-league/other teams (scope, `full-source-ingestion` 0.14).

### 2026-10-07 UTC: tasks 2.8 and 2.2 repaired (MLB bootstrap, after the 404 fix)
- Command: `mlb ingest mlb_api --mode bootstrap` run from a separate checkout at the fixed main (the main checkout has uncommitted owner edits that block a fast-forward). Approval: owner, "yes" (first run) and "yes" (rerun after the fix). About 3 h, no season failures; 46+ read timeouts retried by themselves.
- Before: reference tables missing 2006, 2017-2025 (stats also 2024); mlb_person roster ids missing 147; game pace held 69 seasons.
- After (`mlb coverage --missing-only --unexplained`): reference tables complete 2000-2026 except 2024 for player stat, team stat, stat leader, team leader (that run used the old per-pool skip; the per-table loader fix, PR 364, heals it); roster ids missing 1 (was 147); game pace now 104 seasons (older years the bug had also blocked).
- Not repaired by this run: linescores 84 missing (was 85; the bootstrap treats those seasons as complete) and 2 win-prob/context games in 2011 (game ids 305461 and 308207 answer HTTP 500 at the source on every retry; to be recorded as unavailable if it persists). Next: `mlb ingest mlb_api --stage analytics --start-year 2000 --end-year 2024`, and a bootstrap rerun after PR 364 for 2024 stats.
- Note: the same coverage run, from the worktree, shows retrosheet "CANNOT MEASURE" because a worktree has no downloads/ folder; not a data problem.

### 2026-10-07 UTC: reference loader made self-healing (branch fix/reference-per-table)
- What: the nine MLB reference tables load one at a time (own commit, per-table skip for a past season), replacing one all-or-nothing block keyed on `raw.mlb_player_pool`.
- Why: that block hid the 404 failure for 2006 and 2017-2025 and could never heal a partly loaded season. Rejected: only widening the skip check (would still lose all nine on one error).
- Tests: failing table does not discard others; rerun fetches only missing tables; current season always refetched. mlb_api load tests 50 passed.
### 2026-10-07 UTC: task 2.1 linescores: source has none (branch fix/linescore-unavailable)
- Command: `mlb ingest mlb_api --stage analytics --start-year 2000 --end-year 2024` on production. Approval: owner, "yes run the linescore catch-up". Result: 0 rows loaded. Linescores 3,045,298 before and after.
- Finding (live probes): the 84 missing games answer `game/<pk>/linescore` with HTTP 200 and `innings: []`: 46 are exhibition games (2002-2012), 36 regular-season (2000-2024), 2 special. The source holds no linescore for them, so this is source-unavailable, not a defect to retry.
- Fix: the loader writes a ledger `linescore`/`unavailable` item for each such game and coverage counts it as accounted for; one more analytics run re-hydrates each season once to write the marks (needs approval). Rejected: excluding exhibition games from the expectation (the 36 regular-season games would stay unexplained) and an accepted-gaps ceiling (hides growth).
- Also: 2 games in 2011 (305461, 308207) answer HTTP 500 on win probability and context metrics every retry; to record as unavailable if it persists.

### 2026-10-07 UTC: tasks 2.1 and 2.8 closed
- Commands (production, owner "yes go ahead with both runs"): `mlb ingest mlb_api --mode bootstrap` (stopped by hand after the 2024 stats landed; owner agreed, "we can stop it if you think thats whats best") and `mlb ingest mlb_api --stage analytics --start-year 2000 --end-year 2024`.
- Before: 2024 player/team stats, stat leaders and team leaders missing; 84 linescores missing.
- After: 2024 stats present (1,597 / 60 / 116 / 2,364 rows); 1,353 linescore games recorded in the ledger as `unavailable` (the source returns no innings); `mlb coverage --source mlb_api --unexplained` no longer lists linescores or any reference table.
- Left in mlb_api: 2 games of 2011 (305461, 308207) where winProbability and contextMetrics answer HTTP 500 every time (probed again today); accepted with a ceiling of 2 each. One roster person (116751) not yet in mlb_person; the next mlb_api person load should fetch it.
- Stopped run leaves one `running` row in `meta.ingestion_run`; the nightly `repair-runs` step marks it failed.

### 2026-10-07 UTC: Kalshi and Polymarket backfills deferred (owner: "skip kalshi for now ... its not important right now")
- Review (read-only) of the Kalshi backfill: a real connector (`kalshi.backfill_history`), wired as `mlb ingest kalshi --mode backfill`, tested in `tests/integration/test_kalshi_load.py`. It is idempotent and resumable: one ledger item per market (`candles`: loaded / unavailable / failed) is written in the same transaction as its rows, a rerun skips settled markets, retries failed ones and refetches markets closed under a day; 8 worker threads behind one shared rate limiter; separate source name so it never blocks the nightly. Nothing to rebuild or duplicate.
- Why it looks long: the gap is every market opened since the last backfill (744 earlier, 1,492 now) and it only grows because no schedule runs it. Not run now. Polymarket's backfill has the same shape (not reviewed in detail).
- Open item for later (3.3): a bounded nightly backfill step (a fixed number of newest closed markets per night) so this stops accumulating. Until then the nightly coverage check will report both as unexplained gaps; consider a temporary accepted-gaps ceiling if the alerts become noise (needs owner decision).
