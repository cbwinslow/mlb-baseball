# Session handoff — 2026-09-27

Read this first in a fresh session, then `openspec/project.md`. Written so
nothing from the last session is lost.

## How to work with the owner (do not skip)

- Plain, short language. One decision at a time; plain yes/no for permission
  (repo `CLAUDE.md` "Communicating with the owner").
- The owner said: **handle housekeeping yourself** (closing redundant PRs,
  deleting merged branches, merging green dependency PRs). Do not ask.
- The safety filter blocks Claude from changing the real `mlb` database (even
  with the owner's yes). The owner runs those commands with the `!` prefix.
  Give the exact command; keep it to one line.
- Go slow, be thorough, verify claims against the database and primary sources
  (the owner corrected one wrong claim this session — see Findings).

## Where things stand

- `main` is current (last merged: #254 pipeline fix). Open: **#255** (docs,
  this file included) and draft **#207** (left for the owner).
- Plans on `main`: `openspec/changes/play-engine/` (plate-appearance engine),
  `openspec/changes/pipeline-freshness/`, `model-readiness-audit/`.
- Production `mlb` was caught up by the owner: migration 0107 applied,
  `mlb report` run, `mlb doctor --populated` 9/9.

## Findings this session (evidence in the files named)

1. **Why gold tables kept ending up empty:** the 06:00 daily job ran
   `conform` (empties the backbone, re-issues game ids) and never `report`;
   `conform` also crashed daily from 2026-09-24 on unapplied migration 0107.
   Fixed in #254 (order: migrate gate, update, conform, report only if conform
   ok, predict, `mlb doctor --populated`, per-step timings). Watch the first
   real run: 2026-09-28 06:00 UTC, `logs/mlb_daily_update.log`.
2. **Feature build refuses empty sources** (`feat.EmptySourceError`).
3. **Readiness (game-win v1) is "not ready" on one bounded blocker:** 3,707
   1935–1949 games missing from the play-by-play-built backbone. Rechecked
   against `raw.retrosheet_batting`, box tables and Retrosheet docs: nearly all
   Negro League; 1,547 have full box scores we do not use, 1,889 partial stats,
   271 nothing; 1954/1979 gaps are forfeits. Raw data has no error. Full table:
   `openspec/changes/model-readiness-audit/verification-2026-09-27.md`.
   2015+ has zero unexplained nulls, so the plate-appearance engine is clear.
4. Metric catalog real counts: 39 tracked modules, 50 YAML files.

## Follow-ups (GitHub issues)

- #256 Readiness gate rule for "no full box score" — **owner decision needed**
  (recommended: gate treats it as an explained null; do not cut to 1950+).
- #257 Backbone lines from box scores for the 1,547 box-only games.
- #258 Negro League games in the regular pool; `core.team.league` blank;
  confirm raw-file provenance.
- #259 pipeline-freshness follow-ups (3 clean runs, timing profile, incremental
  go/no-go). Related #84, #70.
- #260 Feature-store freshness (stale `~/.mlb/mlb.duckdb`, games without
  retro id, `DATABASE_URL` default).

## Next steps, in order

1. Merge #255 if still open. Check the 2026-09-28 daily run.
2. Start `play-engine` task 1.1 (verify Retrosheet event-code mapping against
   Chadwick docs and real `core.play` counts), then 1.3 (commit tolerances) and
   1.4 (`mlb_baseball/pa/AGENTS.md`). None needs production writes.
3. Get the owner's decision on #256, implement it, rerun
   `mlb readiness` and close `model-readiness-audit` 4.3.
4. Continue the play-engine ladder per its `tasks.md`.
5. Model wishes (neural, Monte Carlo, Markov to pitches, all three targets,
   model library, publishing tabled): `openspec/changes/play-engine/resume-notes.md`.

## Handy facts

- `openspec` CLI: add `$(/home/cbwinslow/.nvm/versions/node/v24.16.0/bin/npm prefix -g)/bin` to PATH.
- Production URL is in `.env` (`DATABASE_URL`, database name `mlb`); load with
  `set -a && . ./.env && set +a`. Tests use disposable databases only.
- Readiness command: `mlb build --only-features --db <scratch.duckdb>` then
  `mlb readiness --db <scratch.duckdb> --database-url "$DATABASE_URL"`
  (read-only on Postgres). Last scratch file:
  `/tmp/claude-1000/-home-cbwinslow-workspace-mlb/7c57c526-43a1-4876-aef9-61f8db93f52d/scratchpad/readiness.duckdb` (session-local, may be gone).
- CI merges: squash; required checks `test`, `secrets`; branch must be up to
  date; unresolved review threads block merging (resolve after verifying;
  reviewdog SC2016 notes on `workflow-lint.yml` are known false positives).
