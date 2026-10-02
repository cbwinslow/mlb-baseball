# Session handoff — 2026-10-02

Branch: `plan/stable-ids-and-job-retries` (PR #276, planning only, not merged). Untracked `.idea/` is IDE config, not ours.

## Done this session (all merged unless noted)

- PR #273 merged (`d4462b1`): Retrosheet tie-out gate, `mlb ingest --refresh`, `mlb source-check`
  (HEAD requests only, exit 0/1/2), `mlb ingest` now prints `N loaded, M in table`, docs.
- All Retrosheet raw tables refreshed from current files on 2026-10-01; `core`/`gold` rebuilt from
  them (conform + report ran clean). Old downloads are in `downloads/<source>/_superseded/`.
- Tie-out result: 1871–2014 has 26 unexplained differences, all in two Negro League games
  (issue #272); 2015–2025 has the one known game `BOS202509030` (issue #267). Everything else matches.
- Box-score decision (owner): leave out the 1933–1938 Negro League files the reader cannot parse;
  pre-1980 data is low priority. Not yet written into a doc; old rows for those years remain in production.
- `source-change-check` archived into the `source-refresh` spec.
- Weekly cron added: `mlb source-check` Mondays 08:00 → `logs/source_check.log` (crontab backup in the
  old session scratchpad, may be gone).
- Deleted the stale 38 GB dump `backups/mlb_20260817T211259Z.sql` (owner-approved).

## Open work (planning done, no code yet)

PR #276 holds two validated OpenSpec changes. Start with `/opsx:apply job-retries-alerts` (smaller),
then `stable-ids-incremental-conform`.

- **`job-retries-alerts`** (issue #274): `mlb nightly` supervisor (steps as child processes, retry failed
  sources only for `update`, no retry for conform/report/predict), one optional `alert_command` hook,
  `mlb runs [--check]` quick status, `attempt` column on `meta.ingestion_run`.
- **`stable-ids-incremental-conform`** (issue #275): permanent ids (upsert, not truncate), rebuild only
  changed seasons (fingerprints in `meta`), match games to MLB `game_pk` once, `conform --full` as oracle.
  Starts with measuring conform/report/predict per step. Known limit: Elo/predict state chained through
  time is not recomputed forward (stated in the design).

## Findings worth keeping

- Nightly job takes ~2 h 7 min: update 22 m, conform 44 m, report 14 m, predict 47 m (predict not yet
  analyzed). `conform` truncates 23 tables and re-issues every team/player/venue/game id nightly.
- `core.game`: 237,457 games; 75 since 2015 have no MLB `game_pk` (mostly regular-season, 29 in 2020,
  one All-Star per year). Task 4.2 of the stable-ids change examines them.
- Kalshi/Polymarket snapshot tables are append-only (52 daily snapshots since 2026-08-02) but captured
  once a day at 06:00; the intraday candlestick backfill exists and was never run. `captured_at` is TEXT.
- No DB functions/triggers in our schemas; pg_cron installed with 0 jobs; 717 indexes, 1,005 FKs,
  8 unused indexes (~1 GB); 4,857 of 5,007 raw columns are text.
- Playoff/All-Star games: keep one game table with `game_type` (not separate tables); keep season
  totals separate (already done in gold postseason tables).
- Backups: infra job `~/workspace/infra/scripts/validated_backup.sh` dumps every DB nightly
  (mlb = 5.5 GB, verified) to `~/workspace/backups/postgres` on the RAID; mirror at `/srv/backups` on
  the root disk **on purpose** (separate physical disk). Do not move the mirror onto the RAID.
  The repo's own `scripts/mlb_backup.sh` is unscheduled; keep it for other installs.
- Root disk now 82% (95 GB free). Large: `~/lib` 52 GB (owner keeps it; `baseballr-data` is 17 GB),
  `~/.vscode-server` 11 GB, `~/.pybaseball` 9 GB.

## Do first in the new session

1. **Restart cleanup:** I deleted most of `~/.cache` (owner-approved) but also hit the `uv` cache that
   the running MCP servers (browser-use, postgres-mcp) were using. After the restart `uvx` should rebuild
   them; if a tool still errors, check `~/.cache/uv` and rerun. Nothing in project data was touched.
2. Pull latest `main`; PR #276 needs the owner's approval/merge (branch rules require review; the
   auto-mode classifier blocks `--admin` merges and crontab edits unless the owner approves via `/permissions`).
3. `/opsx:apply job-retries-alerts`.

## Not done / not run

- The full test suite was never run; only the targeted tests named in PR #273.
- Weekly `source-check` runs but nothing alerts on its exit code yet (that is the retries change).
- Issue #272 (two 1930s Negro League games) is filed, not resolved; not checked whether Retrosheet documents them
  (its decade discrepancy files cover AL/NL only).

## Ground rules to remember

- Production `mlb` is real data; gate/measurement runs are read-only. Make the target database explicit.
- Keep replies to the owner short and plain (`CLAUDE.md`). Owner wants: clean, short names; fewer, consolidated
  docs; code that is easy to hand to other people and install on another machine; an honest "take a hatchet to it"
  review, not sunk-cost loyalty; industry-standard practice (DBA + software engineer + statistician hats).
- Spec-driven development is OpenSpec (`/opsx:propose` → `/opsx:apply` → `/opsx:archive`); always use it for
  anything beyond a tiny fix.
- Do not merge, force-push, delete branches or edit crontabs without explicit owner approval; if blocked, stop and ask.
