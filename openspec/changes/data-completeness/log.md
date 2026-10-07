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
