# Session handoff — 2026-10-02 (afternoon)

Branch `plan/stable-ids-and-job-retries` (PR #276, not merged; needs the owner's approval).
Untracked `.idea/` is IDE config, not ours. Read `openspec/project.md` after this.

## Update (2026-10-02, evening)

- Pushed `af9162a`: `mlb_baseball/timing.py` + per-step `predict step <name>: Ns` and `report step <name>: Ns` log lines
  (conform already had `conform step ...`). Log-only; tasks 1.1-1.3 are NOT ticked until the 2026-10-03 06:00 UTC log is read.
- Pre-flight done: unit 1,013 + new timing tests pass; **full integration suite passed** (878 passed, 2 skipped, 8 xfail, 25 min).
- Cron runs this unmerged branch checkout (`plan/stable-ids-and-job-retries`); do not switch branches before 06:00 UTC.
- No `mlb.toml`, so no `alert_command`: failures are logged/recorded but nobody is notified. Task 4.2 still open.
- `pg_database_size` caller: roles `metrics_ro` (db `postgres`) and a `cbwinslow` poller on db `promscale`; not mlb, ~4-10 ms/call,
  does not slow the nightly. Program not identified (postgres_exporter target is down). Optional: lower its poll rate.
- Prometheus (localhost:9091) has host CPU/disk history only (no pg stats). Today's predict/report window showed disk waits low
  (1-3%) but writes 150-200 MB/s: theory = ~35 UPDATE passes over `gold.game_feature`. Test against step timings tomorrow.
- Today's totals (no per-step data): core 2,620 s, report 835 s, predict 2,833 s.
- No speed fix exists yet; all speed work is `stable-ids-incremental-conform` tasks 2-6.
- **Next session: "read the run"** = read `logs/mlb_daily_update.log`, `mlb runs`, `meta.query_stat_snapshot`, Postgres log
  `auto_explain` plans; fill `stable-ids-incremental-conform/results.md`; tick 1.1-1.3; propose the first fix (DBA protocol).

## Update 2 (2026-10-02, late)

- Models are blocked only by readiness blocker #256 (3,750 pre-1950 games, ~3,700 Negro League). Owner wants to keep
  pre-2015 data: plan = do `openspec/changes/negro-league-scope/` (proposed, validated, committed `3700eb7`, NOT built),
  keep `game-win-v1` at 1910-2025, pick training years per experiment. Quick alternative (narrow to 2015-2025) was
  offered; owner prefers not to limit. Flag = column on `core.game` + view `core.game_mlb`; rule documented in
  `conform.py.dox.md` + ADR. Raw untouched. Next: `/opsx:apply negro-league-scope` (task 1.1 measure first).
- Retrosheet also publishes `negroleagues.zip` (7 CSVs, 8,215 games, stattype value/lower/upper); we never downloaded it
  (only `allebr.zip`, `allevr.zip`). Count in task 1.1; not needed for the flag.
- Owner's pure-Python Chadwick port is finishing tests; does not solve missing data (no play-by-play to build from).

## Done this session (all committed and pushed to PR #276)

- **`job-retries-alerts` built, tasks 1.1–4.1 + 5.1 ticked** (commits `7f37700`, `2b882d5`, `c9b5715`):
  - `mlb nightly` (`mlb_baseball/nightly.py`): steps as child processes; only `update` retries (3 attempts,
    pauses 60 s / 300 s, failed sources only); one `alert_command` call per failed step; one `meta.ingestion_run`
    row per step attempt (`mode='nightly'`, `attempt`).
  - `mlb runs [--check]` (`runs.py`), `alert_command` (`alert.py`, `config.py`, `mlb.toml.example`),
    `scripts/mlb_daily_update.sh` is now flock + log + `exec mlb nightly` (cron line unchanged).
  - Migrations: `0108` (attempt column, `nightly` mode), `0109` (`meta.query_stat_snapshot`).
  - Nightly now copies `pg_stat_statements` into `meta.query_stat_snapshot` after the steps (180 days kept,
    never fails the run).
  - `conform.run()` now prints `conform step <name>: <N>s` for every step (stable-ids task 1.1 groundwork).
  - Docs: USER_MANUAL "Failure alerts", ARCHITECTURE scheduling paragraph, `cli.py.dox.md`. `openspec validate`
    and `scripts/check_dox.py` pass.
  - Verified: all 1,013 unit tests, 85 conform tests, new integration tests (retry vs real PostgreSQL, runs
    query, attempt column, query snapshot), ruff, mypy. **The full integration suite was never run.**
- **Task 4.2 NOT done** (real `mlb nightly` night recorded in `results.md`; one deliberately failing source
  must trigger exactly one alert on a test config). A real run was started and then stopped by the owner's
  choice (see below).

## Production state (read this before touching anything)

- Migration `0108` is applied on production (the stopped run did `migrate`). `0109` is not; tonight's run applies it.
- I started the nightly by hand at 14:23 UTC and killed it during `update` (conform had not started; core/gold
  untouched). It left `statcast:update` marked `running`; the next nightly's `repair-runs` clears it.
- Today's earlier normal daily run finished 08:07 UTC (conform 2,624 s, report, predict, populated 9/9 ok).
- **Postgres 16 was restarted at 14:54 UTC by the owner** (about 50 s down; data intact, `core.game` = 237,457).
  Now loaded: `pg_stat_statements, pg_cron, timescaledb, age, auto_explain`; `pg_stat_statements.max` 10000;
  `auto_explain.log_min_duration=60s`, `log_analyze=on`, `log_timing=off`, `log_buffers=on`. Plans go to
  `/var/log/postgresql/postgresql-16-main.log`.
- **Gotcha that took the DB down:** `ALTER SYSTEM SET shared_preload_libraries = 'a, b, c'` writes ONE quoted
  string and Postgres then refuses to start ("could not access file 'a, b, c'"). Fix was editing
  `postgresql.auto.conf` with `sed` (comma list, no spaces). `auto_explain.*` settings can only be set after the
  library is loaded (needs the restart first). Do this properly next time.

## Next steps, in order

1. **After tomorrow's 06:00 UTC run** (first run of the new code), read: `logs/mlb_daily_update.log`
   (`conform step ...` timings, `step update ... attempt`), `mlb runs`, `meta.query_stat_snapshot` (first rows),
   and the Postgres log for `auto_explain` plans. Check it exited 0 and the cron shim worked.
2. Then `stable-ids-incremental-conform` tasks 1.1–1.3 (measure conform/predict/report), recording results in its
   `results.md`; only after that, tasks 2+. Owner's goal: make the 2 h 7 min nightly faster
   (baseline: update 22 m, conform 44 m, report 14 m, predict 47 m). `job-retries-alerts` does NOT speed it up;
   the owner was surprised by this, so say it plainly.
3. Finish `job-retries-alerts` 4.2 (record the real night; test the alert hook once), then merge/archive after the
   owner approves PR #276.
4. DBA protocol agreed with the owner: measure → `EXPLAIN (ANALYZE, BUFFERS)` the top costs → change ONE thing →
   re-measure → record. Tools available now: postgres-mcp (`analyze_db_health`, `get_top_queries`,
   `explain_query`, `analyze_workload_indexes`), `hypopg` installed, `pg_stat_statements`, `auto_explain`.
   Not installed (available): `pg_stat_kcache`, `pg_wait_sampling`, `pg_qualstats`, `pgstattuple`, `pg_repack`.
   PostHog was rejected (product analytics, not DB monitoring); Prometheus + Grafana only if charts are wanted later.

## Findings worth keeping

- DB health is fine: index cache hit 99.9 %, table 97.8 %, no bloat, no wraparound risk. The slowness is the
  design (conform truncates 23 tables and re-issues every id nightly; the whole conform is one transaction).
- Old `pg_stat_statements` (max 5000) had evicted conform's big statements, so it could not time them.
- Something calls `SELECT pg_database_size(...)` about 670,000 times (~1 hour cumulative DB time). Find the caller.
- Health check: 9 duplicate indexes (mostly `retrosheet_*__season_idx` vs `idx_retrosheet_*_season`) and ~1 GB of
  never-scanned indexes (e.g. three on `raw.retrosheet_event`, two on `raw.statcast_pitch`). Candidates only;
  verify before dropping.
- My tie-out gate query "per-game flags from the CSV game info" averages ~10 min per call (7 calls). Fine for a
  gate, but know it is the top total-time query.
- `git gc` warns about loose objects (`git prune` would clear it); not done.

## Ground rules to remember

- The auto-mode safety filter blocks me from changing production (SQL writes, `ALTER SYSTEM`, restarts, crontab).
  The owner runs those with the `!` prefix. Give the exact one-line command, and warn about copy-paste slips
  (a trailing `!` broke one command this session).
- Keep replies short and plain (`CLAUDE.md`). The owner wants fewer, consolidated docs, short names, code easy to
  install elsewhere, and an honest "take a hatchet to it" review. The owner got frustrated when I guessed instead of
  showing a method; lead with evidence and a protocol.
- OpenSpec workflow for anything beyond a tiny fix. Do not merge, force-push, delete branches or edit crontabs without
  explicit owner approval. Production `mlb` is real data; make the target database explicit.
- Backups: infra job `~/workspace/infra/scripts/validated_backup.sh` dumps every DB nightly; mirror at `/srv/backups`
  on a separate disk on purpose. The repo's `scripts/mlb_backup.sh` is unscheduled. Root disk 82 % (95 GB free);
  the `mlb` database is 61 GB on `/mnt/storage/postgres-data`.
