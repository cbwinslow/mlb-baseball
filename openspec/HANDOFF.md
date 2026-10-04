> **2026-10-03 update (read first):** active work is `openspec/changes/pipeline-recovery/` (status log in its `results.md`). PRs #276, #279, #280 are merged; cron now runs `mlb nightly` from `main`. First `mlb nightly` run is the 2026-10-03 06:00 UTC job; check it before anything else. The older notes below are from 2026-09-27.

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
