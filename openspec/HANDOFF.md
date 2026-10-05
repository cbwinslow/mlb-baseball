# Session handoff - 2026-10-05 (evening) - read this first in a fresh session

Owner direction: ingest the maximum Polymarket and Kalshi history as fast as the sites allow; keep main
current (merge PRs without asking); build reusable monitoring in PostgreSQL (functions/triggers/procedures
are allowed, ADR-295). Plain, short replies (repo `CLAUDE.md`).

## State

- **Plan:** `openspec/changes/odds-bulk-history/` (tasks ticked as done: 2.1-2.3 run monitor, 3.1-3.4
  Polymarket, 4.1-4.3a Kalshi catalog + candles). Evidence log: `pipeline-recovery/results.md` ("2026-10-05
  afternoon").
- **Polymarket history: done.** 470,754 token-windows loaded, about 598M price points in `raw.polymarket_price`,
  0 failed, 3,256 empty windows remembered in `meta.ingestion_item` (dataset `price_history`). Rerun
  `mlb ingest polymarket --mode backfill` to refresh recent windows and retry failures; it skips settled work.
- **Kalshi:** `raw.kalshi_market` now 890,789 markets back to 2022 (historical listing merged by
  `mlb ingest kalshi --mode update`). Candle backfill `mlb ingest kalshi --mode backfill` is **running**
  (log `logs/kalshi_backfill2.log`, `meta.run_health`), short-lived markets first, about 2 markets/s unsigned.
  It is resumable; if it died, run `mlb repair-runs` then start it again. Owner can create a free Kalshi API
  key and set `KALSHI_API_KEY` + `KALSHI_PRIVATE_KEY_PATH` (PEM file) for about 3x speed. Kalshi trades
  (task 4.3b) not started.
- **Incident:** the first Polymarket backfill held the workflow lock and made the 06:00 nightly fail. Both
  backfills now run under their own source names with no workflow lock. A manual `mlb nightly` was started
  at 13:40 UTC (`logs/nightly_manual_20261005.log`); after it finishes run `mlb build` (stale DuckDB, fixes the
  `feat` health crash) and re-run `mlb doctor`.
- **Do not run local pytest sessions while a long ingest runs.** They force immediate checkpoints on the
  spinning-disk RAID (3-7 minutes each) and stall every writer. Use CI.
- Run monitor: `select * from meta.run_health`, `meta.stuck_runs()`, `meta.op_summary`; doctor check
  "silent ingestion runs".

## Still open

1. Doctor after the nightly: bounds with cited reasons (9.8: bsr wSB 1910-1986 team seasons are real, SIERA,
   pitch movement, platoon), `gbm-v2` model file, catcher framing (owner: hold), prediction counts (re-verify
   after conform).
2. `odds-bulk-history`: 4.3b Kalshi trades, section 5 (Becker/SII datasets: recommended skip, they add
   trade-level data we do not need for price lines), 3.3 Polymarket Gamma field audit and data-api trades,
   3.5/4.4 record counts in results.md, 2.4 (pg_profile only if a measured question needs it).
3. `full-source-ingestion` Phase 0 remaining: 0.3/0.4, 0.6, 0.8-0.10.
4. Owner-run: stop unneeded Docker stacks (the safety filter blocked me); the opendiscourse job is the
   owner's.

---

# Session handoff - 2026-10-05 (late) - read this first in a fresh session

Owner direction today: collect EVERY lawful free pro data source, all endpoints, all columns, kept
separate per source in `raw`; no paid providers; minors/college last; do not disturb working connectors.
Keep replies short, plain, one decision at a time (repo `CLAUDE.md`).

## Durable work map — where the next task comes from

This handoff is **session state and routing**, not the master backlog. A fresh
agent should use these owners instead of copying tasks out of chat history:

1. **Project priority / phase gate:** `openspec/project.md` (`NOW / NEXT / LATER`).
2. **Current execution state:** this file, `openspec/HANDOFF.md`.
3. **Authoritative checklists:** the owning
   `openspec/changes/<change>/tasks.md`; do not duplicate those checkboxes here.
4. **Platform exit gate:** `docs/PRODUCTION_CONVERGENCE.md`.
5. **Outside-review disposition / future backlog:** `chatgpt/README.md` and
   `openspec/changes/governance-convergence/design.md` D8-D10. The raw
   `chatgpt/*.md` reviews are evidence, not task instructions.

### Pull-next-task rule for Claude/agents

- Finish the highest-priority unblocked task in the current owning change.
- If it is blocked on owner approval, an external wait, or a scheduled run,
  move to the next non-overlapping lane below rather than inventing work.
- When a change finishes, update its evidence/results, `openspec/project.md`
  status, and this handoff, then archive it through OpenSpec.
- Do not start a named future change from the review map merely because it
  exists; current phase gates still apply.

### Current execution lanes

| Priority | Lane | Canonical checklist | Rule |
|---|---|---|---|
| 1 | Platform recovery / correctness | `openspec/changes/pipeline-recovery/tasks.md` | Close real/wrong health defects and recovery prerequisites first. |
| 1a | Source-completeness planning | `openspec/changes/full-source-ingestion/tasks.md` Phase 0 | Planning/inventory may proceed in parallel, but task 0.1 explicitly says it must not delay `pipeline-recovery`. Do not let broad ingestion expansion hide foundation defects. |
| 1b | Odds history operations | `openspec/changes/odds-history-capture/tasks.md` | Mostly waits on the running backfill / observation window; record evidence when it completes. |
| 2 | Stable identity + incremental conform | `openspec/changes/stable-ids-incremental-conform/tasks.md` | Starts after the recovery/spec-strengthening prerequisites are satisfied. |
| 2b | Model readiness blocker | `openspec/changes/model-readiness-audit/tasks.md` task 4.3 | Resume only after its bounded data/null-policy blocker is resolved. |
| 3 | Formula/SQL convergence | `docs/SQL_OWNERSHIP.md` + future bounded OpenSpec work | After Platform Convergence prerequisites: inventory first; wOBA/wRC+, FIP/xFIP, then RE24/WPA. |
| Later | Library/source evaluation, target registry, market contracts, research lineage, model promotion | `chatgpt/README.md` + governance-convergence D8-D10 | Future work only; create/extend an OpenSpec change when the current phase permits it. |

There is intentionally **no second master checklist**. The table above tells an
agent where to pull the next real checkbox from.

## What happened this session

- Merged: #308 (doctor shows crashed checks as ERROR), #309 (prediction-coverage checks count games),
  #310 (audit doc `docs/SOURCE_COVERAGE_AUDIT.md`), #311 (generated `docs/RAW_INVENTORY.md` +
  `mlb inventory --markdown`), #312 (OpenSpec change `full-source-ingestion`, planning only, incl. task 0.10
  `mlb coverage` finder). **#313** (one-time ledger seeding code) stays UNMERGED by owner decision: one-time
  imports do not live in the repo; the owner may close it.
- One-time analytics restore DONE on production `mlb` (owner yes): the win-probability responses were never
  saved on this server (loaded 2026-07-28/29, saving code came 2026-08-09); the laptop `cbwlap1`
  (LAN 192.168.6.166) had them. Copied to `~/workspace/mlb/downloads/mlb_api/` (946 files, sha256 verified),
  ledger rebuilt (330,440 rows) and raw reloaded from the files (no network). Win-prob games 164,362 ->
  164,589; linescore 3.01M -> 3.04M. Evidence: `pipeline-recovery/results.md` (PR **#314**, open, docs only).
  `mlb_api_scratch` (the laptop's parsed copy, on this server) can stay or be dropped.
- Left over from it: doctor `mlb_api analytics durable coverage` fails on 2 seasons, 5 final games with no
  saved response: 1999 (3) and 2011 (2). Fix: `mlb ingest mlb_api --stage analytics --start-year 1999
  --end-year 1999` (then 2011); fetches only those games. Needs the owner's yes (production write). Then tick
  `pipeline-recovery` 9.5.
- Odds: Polymarket then Kalshi history backfill is one background chain
  (`~/workspace/mlb/logs/odds_backfill.log`, look for `polymarket rc=` / `kalshi rc=`; Polymarket was retrying
  `clob.polymarket.com` read timeouts); cron `*/15 odds_capture.sh` is installed and runs (rc=0). When the
  chain ends, log it in `results.md` and tick odds-history-capture 4.2/4.3/5.2 (then 5.3 after a week, 6.1).
- Audit facts: `mlb_api` is MLB-only (`sportId=1`); pre-2026 play-by-play, box scores, per-pitch GUMBO feed,
  weather/officials hydrates, extra stat groups and minors are not ingested (ADR-017/018/019 "skip,
  redundant", to be superseded). Only Retrosheet, Lahman and MLB analytics save downloads first; Statcast,
  FanGraphs, BBRef, register, Kalshi/Polymarket, news load from memory: owner decision is to leave working
  connectors alone and use save-first only for NEW datasets (task 0.11).

## Waiting on the owner

1. Yes/no: fetch the 5 missing games (1999, 2011), see above.
2. Catcher framing (9.4): owner said hold off.
3. Owner-run, one-time: `mlb build` (stale DuckDB, 9.6), `mlb catalog build` (2.7), `VACUUM (ANALYZE)` of four
   raw tables (2.8).

## Next steps (in order)

1. **Close `pipeline-recovery` blockers first.** Finish the five-game analytics
   ledger gap if the owner approves the write, then 9.8 wrong-check bounds with
   cited/data-backed reasons, the remaining doctor/recovery items, and the
   measurement/spec-strengthening work that gates stable IDs. The owning
   checklist is `openspec/changes/pipeline-recovery/tasks.md`.
2. **In parallel only where it does not delay recovery, continue
   `full-source-ingestion` Phase 0 planning**: 0.1 record the owner direction
   in `openspec/project.md`; verify the MLB OpenAPI/terms; measure one feed
   season; create source coverage pages; record the redundancy-policy ADR; build
   `mlb coverage`. Do not treat Phase 0 planning as permission to skip
   Platform Convergence defects.
3. **Finish odds-history evidence when the running work allows it.** After the
   backfill and next conform, re-check the 55 decided games with a live-snapshot
   prediction but no `core.market` Polymarket row
   (`pipeline-recovery/results.md`, 9.9). If they remain, treat it as a conform
   bug. Complete the owning `odds-history-capture/tasks.md` evidence as its
   observation windows mature.
4. **Then execute `stable-ids-incremental-conform`.** Do not re-design it from
   chat: use its `tasks.md`, after `pipeline-recovery` section 6 has
   strengthened the spec and the measured baselines exist.
5. **After Platform Convergence foundation work is green, pull the next
   architecture/research task from `openspec/project.md` and the review
   disposition map.** The first intended formula-convergence family is
   wOBA/wRC+ and FIP/xFIP, followed by RE24/WPA; library/source evaluation and
   broader model/market work remain phase-gated.

## Practical notes

- Worktree for this work: `~/workspace/mlb-doctor-error` (own `.venv`, `uv sync --all-extras` done; branches
  per change off `origin/main`). `~/workspace/mlb` must stay on `main`.
- `openspec` CLI: `npx --no-install openspec ...`. A failed pre-commit hook (end-of-file) aborts the commit:
  re-add and commit again. A trailing period or doubled `!` in an owner-pasted command breaks it.
- Do not use planner row estimates (`pg_stat_user_tables`) for "is this table empty": use `count(*)`.
- A claim of "paid/blocked" etc. from a subagent is evidence, not proof; re-verify.

---

# Session handoff — 2026-10-05 (read this first in a fresh session)

Active work: `openspec/changes/pipeline-recovery/` (log in `results.md`) and
`openspec/changes/odds-history-capture/` (tasks.md). The owner's standard still applies: fix every
error at its source, no patches, a test that fails at the cause first. Keep replies short and plain.

## State as of 2026-10-05

- **Nightly run:** the 2026-10-04 06:00 run passed (rc=0, ~2 h). Doctor 355/370 (353 on a second pass).
  `away_woba coverage` and `starter first-pitch strike%` now pass. Remaining failures: backup check
  (wrong: host job does backups), prediction counts x2 (check or join fan-out, undiagnosed), `feat`
  health check crashes on missing column `home_pa_30d`, gbm-v2 model file, empty metric catalog,
  mlb_api analytics ledger (1950s source limit), bsr / catcher framing (61,107 bad values) /
  pitcher estimator / pitch movement / platoon bounds, never-vacuumed tables. The two
  `raw.kalshi_candle` / `raw.polymarket_price` failures are now "backfill not run" passes (ADR-294).
- **Merged today:** #294 (archived raw-source-tieout, pure-python-retrosheet, team-franchise-crosswalk),
  #295 (odds plan), #296 (odds capture: catalog rows kept via `upsert_dataframe`, `snapshot()` per
  source, `mlb odds-capture`, `scripts/mlb_odds_capture.sh`, migration 0110, doctor `check_snapshot_gaps`
  / `check_backfill_state`, ADR-294).
- **odds-history-capture is NOT finished.** Waiting on the owner's yes: 4.2/4.3 run the Polymarket and
  Kalshi history backfills on production (`mlb ingest polymarket --mode backfill`, then kalshi); 5.2
  install the cron line `*/15 * * * * ~/workspace/mlb/scripts/mlb_odds_capture.sh`. Then 5.3 (review
  row volume after a week; measured 3,008 Kalshi + 5,314 Polymarket rows per capture) and 6.1 (archive).
  Log every production write in `pipeline-recovery/results.md`. Until the cron runs, the snapshot gap
  check will fail on game days.
- **Next after that:** catcher framing (9.4: rebuild from real pitch data or withhold columns; the
  owner decides), the `feat` crash, prediction-count checks, sibling live-update SQL audit (9.2b),
  empty ingestion ledger (9.5), wrong checks with cited reasons (9.8, 9.9), then the speed work.
- **Open housekeeping:** `feature-store-v1` will not archive (its delta spec would drop four model-card
  scenarios; merge them into the delta, then `openspec archive`). PRs #285/#286/#287 (CodeQL action
  bumps; two have a failing check), #271 (uv deps), #261 (probably redundant after #294), #207 (owner's).
- **Merging:** the owner added `Bash(gh pr merge:*)` to global permissions. Squash-merge when checks
  are green and review threads resolved. `~/.claude/settings.json` edits are blocked for Claude.

## Practical notes (new)

- Worktree for this work: `~/workspace/mlb-odds-capture` (own `.venv`; `.env` copied in). The main
  checkout `~/workspace/mlb` **must stay on `main`** (cron runs from it; `git pull --ff-only`).
- The full pytest suite takes ~26 min. 25 `packages/retrosheetpy` tests fail locally (also on clean
  main) but pass in CI; ignore them locally. Run targeted files while working.
- Never wait with `read -t` on empty input (returns instantly); poll with `timeout 10 tail -f /dev/null`.
- Never `pkill -f "pytest ..."` from a shell whose command line contains that text (kills itself).
- A test that reads `raw.*` with `db_conn` must `rollback()` before the code under test truncates that
  table, or it deadlocks.
- Reference-only below: older notes from 2026-10-04 and 2026-09-27.

# Session handoff — 2026-10-04 (read this first in a fresh session)

Then read `openspec/project.md`, then `openspec/changes/pipeline-recovery/` (`tasks.md` is the
worklist, `results.md` is the evidence log with every finding and approval, `design.md` D9-D11 are
the rules). The older notes from 2026-09-27 are kept below.

## How to work with the owner (do not skip)

- Plain, short language; lead with one sentence the owner can act on. One decision at a time,
  plain yes/no for permission (repo `CLAUDE.md`, "Communicating with the owner").
- **The owner's standard (2026-10-03): trace every error to its source and fix it there. No
  splintered patches. A health-check bound is widened only with a written, cited reason.** If that
  cannot be done the owner will consider gutting workflows. Every fix needs a test that fails
  at the cause first.
- The owner asked me to merge their PRs ("commit and merge our code and solutions"): squash-merge
  when `test` + `secrets` are green and every review thread is resolved (main requires conversation
  resolution and an up-to-date branch). Reply to and resolve CodeRabbit threads after fixing them.
- Production is `mlb`, tests use run-specific temp databases (`mlb_test_*`); never point pytest at
  `mlb`. So far no write to `mlb` was blocked; every production write is described in plain words
  first, then logged in `results.md`.

## What happened 2026-10-02 to 2026-10-04

- Decided ONE speed approach (option A: stable ids + per-season incremental conform, from
  `openspec/changes/stable-ids-incremental-conform/`). Shadow-schema swap = fallback only; SQLMesh
  for conform = rejected (ADR-088/266/271). Panel evidence: Codex + Grok + four doc reviews.
- Merged PRs: #276 (stable-ids + job-retries plan, `mlb nightly` supervisor, timing logs, migration
  0109, with review fixes: step timeout, repair-runs timeout, CLI dispatch test), #279 (bref window
  ends before the first postseason game: 2026 playoff leak fixed), #280/#281/#283/#284/#288/#290
  (pipeline-recovery docs), #289 (runs test clock was a time bomb), #291 (`away_woba` overwrite
  fix), #292 (pitch-discipline double count, ADR-293).
- First `mlb nightly` run (2026-10-03 06:00-08:00 UTC): rc=0, ~2 h; doctor 353/370. The 06:00 cron
  runs `scripts/mlb_daily_update.sh` -> `mlb nightly` from `~/workspace/mlb`, **which must stay on
  `main`** (it was switched back; pull before each session: `git pull --ff-only origin main`).
- Backups already exist: host job `~/workspace/infra/scripts/validated_backup.sh` dumps `mlb`
  nightly 02:00 (5.6 GB `-Fc`, `~/workspace/backups/postgres/daily/<stamp>/pg16_mlb.dump`,
  mirrored). A restore test passed (23.5 min into `mlb_restore_check`, since dropped). The database
  disk is `/mnt/storage` (840 GB free), not `/`. Doctor's "backup never run" is a wrong check.

## Where things stand (17 doctor failures at the last run; 2 more should clear after tonight's run)

Real defects fixed at source: playoff leak (#279), `away_woba` (#291), pitch-sequence double count
(#292). **Check after the 2026-10-04 06:00 run:** doctor `away_woba coverage` and
`starter first-pitch strike%` should pass.

Open, in priority order (details in `tasks.md` / `results.md` section 1.5):
1. Audit sibling live-update SQL for the same home-only gating (9.2b): `team_starter_live`,
   `team_bullpen_live`, `starter_workload_live` (read-only first).
2. Empty ingestion ledger `meta.ingestion_item` (9.5): check the loader's ledger write path
   (`mlb_api.py` ~1528, 1697-1788), fix, then backfill from existing raw. 1950s gaps are a source
   limit.
3. **Catcher framing (9.4) needs the owner's decision:** feature counts "called strikes" from play
   text (`event_tx LIKE '%C%'`), i.e. wrong. Either rebuild from real pitch data (Statcast
   `called_strike` / Retrosheet pitch sequence) or withhold the columns. Do not widen the bound.
4. Wrong checks to correct with cited reasons (9.8, 9.9): bsr `wsb` bound, SIERA lower bound,
   pitch-movement separation bound, platoon diff bound, prediction-count check (count distinct
   games; Polymarket 584 vs 538 gap unexplained). Also `COALESCE(...,0.320)` in the platoon SQL
   fills missing wOBA (conflicts with "missing is not zero").
5. Stale `~/.mlb/mlb.duckdb` -> `mlb build` (9.6). Metric catalog empty -> `mlb catalog build`
   (2.7). One-off `VACUUM (ANALYZE)` of four raw tables (2.8). Doctor backup check should read the
   host backup (2.4; owner to decide keep/retire `mlb backup`). gbm-v2 model file missing
   (owner: accept?).
6. Open question for the owner: `raw.kalshi_market` is replaced whole each run (lost 14,594 rows
   between 02:32 and 06:08 on 2026-10-03). Intended? History is in `raw.kalshi_snapshot`.
7. Owner sign-off on the doctor classification (1.5), validation-gate ADR (9.7: `implemented-
   untested` metrics must not feed model inputs; 16 of 50 are untested, 1 validated).
8. Speed work (sections 4-7): measure first (pg_stat_statements reset, lock waits), store timings
   in a `meta` table (5.1), fix the four gaps in the stable-ids spec (6.x), then implement it.
   Baseline: update 14-22 min, conform 43 min, report 14 min, predict 49 min (~2 h).

## Practical notes for the next session

- Work in a worktree, not the shared checkout: `~/workspace/mlb-fix-bref-window` (own `.venv`;
  run tests with `.venv/bin/python -m pytest ...`; `uv run pytest` there can pick the wrong
  pytest). One branch per change off `origin/main`.
- `gh pr update-branch` does not exist here: merge `origin/main` into the branch and push.
  Foreground `sleep` is blocked: poll in a `for` loop around `gh pr checks`, and `mlb doctor`
  takes 3-5 minutes (run it in the background).
- Tests that create their own `raw.retrosheet_event` must include every column a module reads.
- Subagent reports are evidence, not proof: re-verify key claims against the code/data.
- Another session may be working in `~/workspace/mlb-pure-python` (retrosheetpy); stay out of it.

---

# Session handoff — 2026-09-27 (evening)

Read this first in a fresh session, then `openspec/project.md`. Replaces the
earlier 2026-09-27 handoff (its still-valid parts are kept below).

## How to work with the owner (do not skip)

- Plain, short language. One decision at a time; plain yes/no for permission
  (repo `CLAUDE.md` "Communicating with the owner").
- The owner said: **handle housekeeping yourself** (closing redundant PRs,
  deleting merged branches, merging green dependency PRs). Do not ask.
- The safety filter blocks Claude from changing the real `mlb` database (even
  with the owner's yes). The owner runs those commands with the `!` prefix.
  Give the exact command; keep it to one line.
- Go slow, be thorough, verify claims against the database and primary sources.
- The owner gets nervous when raw data or ingestion might be compromised, and
  when the same question is reopened. **Check `docs/DECISIONS.md` and prior
  changes before treating anything as open** (this session I wrongly left
  postseason handling "to decide"; ADR-283 already decides it: models use
  regular-season games only, postseason in a model input is a leakage defect).
- Do not change raw tables or ingestion code as a side effect of model work.

## Where things stand

- `main` is current (last merged: #255). Draft #207 is left for the owner.
- Two branches are pushed with **no merge yet** (open PRs if not already open):
  1. `docs/raw-source-tieout` — new change `openspec/changes/raw-source-tieout/`
     (planning only, validated). **The owner chose this as the next thing to build.**
  2. `docs/play-engine-event-mapping` — play-engine task 1.1 done (event-code
     mapping verified, ADR-283 postseason scope, raw-source tie-out evidence
     recorded in `play-engine/design.md`; task ticked).
- Production `mlb` is caught up (migration 0107, `mlb report`, `mlb doctor
  --populated` 9/9). The 06:00 UTC daily job on **2026-09-28** is the first run
  of the #254 fix: check `logs/mlb_daily_update.log`.

## What I verified this session (read-only, production `mlb`)

- Event codes {2, 3, 14–23} equal Chadwick's own `bat_event_fl='T'` set exactly;
  per-season counts equal `core.play` for 2015–2025 (1,939,010 plate
  appearances). Codes 4–13 are baserunning. Rates look right (K 20.5–23.6%,
  HR 2.7–3.6%).
- Events (`raw.retrosheet_event`) and Retrosheet's CSV batting
  (`raw.retrosheet_batting`) agree **exactly** on PA, K, HR for every season
  2015–2025. Game logs are regular season only and run lower on HR by exactly the
  postseason total in `raw.retrosheet_gamelog_post` (94, 97, 159, 116 checked).
- Box scores (`raw.retrosheet_box_*`) only cover 1871–1961; they cannot check
  modern seasons.
- `core.play` Retrosheet rows for 2015–2025 have **null** outs, balls, strikes
  and scores. Base-out state must come from `raw.retrosheet_event` (`outs_ct`,
  `start_bases_cd`, never null) joined by game and `event_id` = `play_index`.
  `raw.retrosheet_event` also has `bat_hand_cd` / `pit_hand_cd` on every row.
- `raw.retrosheet_plays` (CSV play-by-play, 16.7M rows) is slow to scan; a
  season-filtered count timed out at the 30-second MCP limit. Use a longer
  timeout from a script or run in the background. Its `_season` column is text
  (cast with `::int`); `retrosheet_gamelog_post` has no `_season` (use
  `left(date,4)`).
- Existing Retrosheet loader tests prove landing, reload scope and missing
  input, not content correctness. There is no integration test loading
  `retrosheet_event`, and nothing compares two sources.

## Next steps, in order

1. Check the 2026-09-28 daily run. Open/merge the two PRs above once CI is green
   (squash; required checks `test`, `secrets`; branch must be up to date).
2. **Build `raw-source-tieout`** with `/opsx:apply raw-source-tieout`, starting at
   task 1.1 (test audit `audit.md`), then 1.2, 1.3 (commit the pass marks before
   the full run), then the gate (section 2), test gaps (3), the production
   read-only run (4). It never writes to `raw`/`core`/`gold`; differences found
   become issues, not fixes.
3. Then return to `play-engine` (parked, 1/22 done): tasks 1.3 (commit
   tolerances — propose numbers, the owner approves) and 1.4
   (`mlb_baseball/pa/AGENTS.md`). Its first dataset build (2.3) waits for a
   passing tie-out on 2015–2025 and must use the raw event table for base-out
   state and filter to regular season (ADR-283).
4. Owner decision still needed on **#256** (readiness gate rule for "no full box
   score"; recommended: treat as an explained null; do not cut to 1950+). Then
   rerun `mlb readiness` and close `model-readiness-audit` 4.3.
5. Model wishes tabled (neural, Monte Carlo, Markov to pitches, publishing):
   `openspec/changes/play-engine/resume-notes.md`.

## Open issues

- #256 readiness gate rule (owner decision), #257 backbone lines for 1,586
  box-only games, #258 Negro League games in the regular pool, #259
  pipeline-freshness follow-ups, #260 feature-store freshness.

## Handy facts

- `openspec` CLI: add `$(/home/cbwinslow/.nvm/versions/node/v24.16.0/bin/npm prefix -g)/bin` to PATH.
- Production URL is in `.env` (`DATABASE_URL`, database name `mlb`); load with
  `set -a && . ./.env && set +a`. Tests use disposable databases only.
- The Postgres MCP tools (`postgres-mlb`) are read-only with a 30-second query limit.
- Readiness command: `mlb build --only-features --db <scratch.duckdb>` then
  `mlb readiness --db <scratch.duckdb> --database-url "$DATABASE_URL"`.
- Pattern for a read-only gate: `scripts/verify_mlb_boxscore_tie_out.py`
  (tested in `tests/unit/test_boxscore_tie_out.py`). `scripts/AGENTS.md`: reusable
  logic goes in the package, scripts stay thin.
- CI merges: squash; unresolved review threads block merging (reviewdog SC2016
  notes on `workflow-lint.yml` are known false positives).
