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
