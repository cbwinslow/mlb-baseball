# Architecture

Scope: System architecture overview across ingestion, relational core, derived gold models, and serving layers. Implementation is governed by the active plans under `plans/` and durable doctrine in `AGENTS.md` (see also [NORTH_STAR.md](NORTH_STAR.md)).

## Database

Single Postgres instance, addressed via `DATABASE_URL` in `.env` (see [DECISIONS.md](DECISIONS.md) ADR-002). No assumption about how Postgres is hosted — bare-metal is the expected default, nothing requires Docker.

### Extensions

The Postgres cluster this project's database lives on also hosts unrelated work (a `bronze` schema/`news_raw` table belonging to something else entirely) and has ~70 extensions available, several already installed cluster-wide (PostGIS, Apache AGE, pgvector, TimescaleDB, pg_trgm, pg_cron, btree_gist) — leftover from evaluating them for the prior (since-scrapped) version of this project, not a signal that this rebuild should use them. Evaluated directly (ADR-043) rather than adopted by default, per this project's standing bias against speculative infrastructure (see "Explicitly not designed yet" below):

- **`pg_stat_statements`** — adopted. Already loaded via `shared_preload_libraries`; migration 0024 creates the extension in every database this project migrates. `mlb doctor` checks it's actually tracking (ADR-043). This is the real tool behind "is a query actually slow," replacing guesswork — but its data is cluster-wide, not scoped to this project's schemas, so any investigation using it has to filter out the unrelated `bronze` workload manually, not trust an aggregate ranking at face value.
- **TimescaleDB (2.28, already installed)** — evaluated for `core.pitch`/`core.play` and declined for now. Converting 13-16M-row, already season-partitioned tables into hypertables is a real, hard-to-reverse migration (new PK shape, chunk retuning) with no identified query pattern (rolling time-range analysis) that the current season-partitioning doesn't already serve. Revisit if a genuine time-range-heavy access pattern shows up.
- **`pg_trgm`** — available, not wired into `conform.py`. Team/player identity resolution in this project is deliberately ID-based (Chadwick's crosswalk, `core.team.mlb_team_id`), not fuzzy string matching — see ADR-029's explicit reasoning for why `core.team_alias` stays a small, source-verified seed list rather than a general name-reconciliation table. Fuzzy matching would cut against that design, not complement it. Worth having for one-off exploratory/research queries (e.g., ad-hoc "find players named similarly to X"), not the ingestion pipeline itself.
- **`pgvector`** — available, nothing to store yet. Relevant once a Phase 2/3 feature genuinely needs similarity search (e.g. play-style or pitch-arsenal embeddings) — `gold` schema is explicitly reserved and deliberately empty until then (see below).
- **`hypopg`** — not installed. A session-scoped "what if I added this index" dev tool, useful for future index-tuning work without committing to a real index first; no standing dependency either way.
- **PostGIS, Apache AGE** — not used, no plan to use them. No geospatial or graph-shaped query pattern exists in this project (core.venue's lat/long columns are stored but not spatially queried). Confirmed by the project owner these were installed for the prior, scrapped version of this project, not a forward-looking signal for this one.
- **pageinspect/pgstattuple/pg_buffercache/amcheck** and similar low-level introspection extensions — not wired into anything; available for ad-hoc DBA investigation if a real need comes up (bloat, corruption, cache-hit troubleshooting), not worth a standing health check given how rarely they'd fire.

## Layered schema (Medallion-style)

- **`raw`** — source-faithful tables, one per upstream source, minimally reshaped, deliberately untyped (`text` columns, no PK/FK/constraints — see `mlb_baseball/load.py`). Event-stream sources (Retrosheet, Statcast, MLB Stats API) land append-only; snapshot sources (the Chadwick register) truncate-and-reload each run instead, since there's no meaningful "new rows since last time" for a full-snapshot source (see Connector contract below). Staying untyped is what lets raw tolerate schema drift from a source without breaking (e.g. `load_dataframe`'s `ALTER TABLE ADD COLUMN` for a later batch with columns an earlier one didn't have) — raw data doesn't need to be re-fetched just because a downstream transform has a bug.
- **`core`** — real relational structure: surrogate primary keys, foreign keys, indices. Built by joining already-landed `raw` tables against the Chadwick ID crosswalk so every player/team/game reference is consistent across sources — Kimball's "conformed dimensions," which is where the schema's original name (`conformed`, renamed to `core` — see ADR-013) came from. `core.player`/`core.team`/`core.game` are the dimensions; `core.play`/`core.pitch` are the facts (one row per plate appearance/tracked pitch, unifying Retrosheet+MLB API and Statcast respectively — ADR-017/018); `core.market` (one row per Polymarket/Kalshi market, matched to a game — ADR-028) and `core.player_war` (Baseball-Reference's own WAR, one row per player-season-stint — ADR-028) are the newest additions, closing the gap where this project's stated differentiator (market-implied probabilities, see `NORTH_STAR.md`) sat in `raw` with no bridge to `core` at all. `core.team` also carries `mlb_team_id` (MLB Stats API's own stable numeric team ID, the team equivalent of `core.player.mlbam_id`), with a small `core.team_alias` table covering the one case with no shared numeric ID at all — Polymarket/Kalshi (ADR-029). `core.venue` (one row per historical ballpark, keyed on Retrosheet's own `parkid`, enriched from MLB's venue catalog by exact name match) and `core.standing` (one row per team-season, 1969+) are the newest additions (ADR-030), closing the same "landed in raw, never bridged to core" gap for `raw.retrosheet_park`/`raw.mlb_venue`/`raw.mlb_standing`; `core.game` also gained Retrosheet's own per-game weather columns in the same change. This is the layer modeling (Phase 2) and the website (Phase 3) are expected to consume — not raw.
- **`gold`** — derived baseball statistics, feature families, immutable feature snapshots, baseline/model tables, and evaluation outputs (see `AGENTS.md` and `docs/TABLE_CONTRACTS.md`). `gold.game_feature` serves as the primary completed-and-scheduled consumer-demand relation. Narrow domain feature families and named SQLMesh models are preferred over wide, sparse tables. A separate **reporting surface** (ADR-057, `mlb_baseball/report.py`, `mlb report` — not yet wired into the CLI, see that ADR) also lives here: `gold.player_season`, `gold.team_season`, `gold.division_standing` (migration `0030_gold_reporting.sql`) — one flat table per entity/grain, built from already-conformed `core` plus already-computed `model/*.py` season aggregates, so a future Phase 3 API/website can query one table per page instead of assembling from a dozen raw/core tables at request time. Deliberately carry **no** FK to `core.player`/`core.team` — see ADR-057 for why (a real constraint from `conform.py`'s own consolidated `TRUNCATE` statement, not a style choice).

`core` is populated by `mlb_baseball/conform.py` (`mlb conform`), not a connector — see "Conform contract" below.

## Connector contract

This project is a reusable ingestion toolkit, not a one-shot script — the goal is that a stranger can clone the repo, bootstrap the full database from nothing, and keep it updated afterward, the same way `pybaseball` gives reusable access to Statcast/FanGraphs/Bref. Every source in [DATA_SOURCES.md](DATA_SOURCES.md) gets a connector module under `mlb_baseball/connectors/` that exposes exactly two functions, both returning `dict[str, int]` of `{table: row_count}`:

- **`bootstrap()`** — full historical load, from nothing. What a new user runs once.
- **`update()`** — incremental: pull what's new since the last run. What gets run on a schedule for maintenance.

For sources distributed as a full snapshot (e.g. the Chadwick register), `bootstrap()` and `update()` are legitimately the same operation — both do a full truncate-and-reload. For sources with real incremental structure (Statcast, MLB Stats API), they differ: `update()` should only pull the recent window, not replay history.

Every run — from either function — is wrapped in `mlb_baseball.ingest.track_run()`, which logs to `meta.ingestion_run` (source, mode, status, row counts, errors, timestamps). This is what makes bootstrapping and maintenance observable instead of a black box: `SELECT * FROM meta.ingestion_run ORDER BY started_at DESC` shows what ran and whether it worked.

Every connector also exposes a third function: **`health_check() -> list[Check]`**, using the shared helpers in `mlb_baseball/health.py`. This is what `mlb doctor` calls to answer "is everything actually working?" in one command — see CLAUDE.md "Operational health checks". Not optional: `tests/unit/test_cli_registry.py::test_all_connectors_expose_health_check` enforces it.

A fourth, genuinely optional function — **`backfill_history() -> dict[str, int]`** — exists for sources with a one-off historical operation too expensive to run as part of `bootstrap()`/`update()` (`polymarket.py`/`kalshi.py`'s intraday price-history/candlestick backfills, ADR-049). Unlike the three functions above, this isn't required of every connector: `mlb ingest <source> --mode backfill` dispatches to it via `getattr(connector, "backfill_history", None)` and fails clearly if the connector doesn't implement one, rather than every connector needing a no-op stub. `meta.ingestion_run.mode` has a `'backfill'` value alongside `'bootstrap'`/`'update'` for this (migration `0028_ingestion_run_backfill_mode.sql`).

Connectors are independent of each other; the Chadwick ID crosswalk is what ties their outputs together during conforming, not the connectors themselves. All of them are driven through one CLI registered in `mlb_baseball/cli.py` — not separate one-off scripts per source:

- `mlb ingest <source> --mode bootstrap|update|backfill` — run a connector (`backfill` only where implemented, see above)
- `mlb ingest mlb_api --stage analytics --start-year YEAR --end-year YEAR --workers 1..16` — run the high-volume win-probability/context stage independently. Each batch archives compressed JSON, replaces only its successful game keys with COPY, and records terminal per-game endpoint status in `meta.ingestion_item`; a rerun skips durable loaded and confirmed-unavailable items.
- `mlb ingest mlb_api --stage analytics-replay --start-year YEAR --end-year YEAR` — rebuild that stage from the ledger-referenced, checksum-verified local artifacts without contacting MLB.
- `scripts/mlb_api_backfill.sh` — owner-triggered full Stats API posture command: migrations, the resumable analytics stage, then the remaining schedule/reference/catalog bootstrap under one `flock`. It is the supported operational path for recreating the complete MLB API raw layer; the five-minute update script is intentionally not a substitute for it.
- `mlb conform` — rebuild `core` from already-ingested `raw` data (see "Conform contract" below)
- `mlb inventory` — live table/row-count report plus last run per source, queried fresh every time (a static doc would go stale immediately with this many tables)
- `mlb metrics --source SOURCE --window-minutes 1..60` — read-only ingestion/database snapshot: recent durable-item throughput, cache hit rate, connection count, and the active MLB API raw tables' size, dead-row estimate, and scan mix. Use this before tuning a loader so a slow upstream API is not mistaken for slow PostgreSQL writes.
- `mlb doctor` — DB connectivity, schema/migration state, and every connector's `health_check()` in one pass

## Conform contract

`mlb_baseball/conform.py` builds `core` from `raw` — a transform, not a connector: it never touches the network, has no `bootstrap()`/`update()` split, and isn't in `mlb_baseball/registry.py`'s `CONNECTORS` (so it doesn't show up under `mlb ingest <source>`; it's its own `mlb conform` subcommand). One `run()` entry point does a full truncate-and-rebuild every time — simplest-correct at `core`'s current row count (~225K games), matching CLAUDE.md's "prefer explicit, boring code" guidance over a more complex incremental-diff approach.

Before rebuilding, `run()` checks that the `raw` tables it depends on actually have data (`_check_prerequisites()`), raising an actionable error (naming the `mlb ingest ... --mode bootstrap` command to fix it) rather than either running silently on empty raw tables or failing mid-join with a confusing error. Like every other fresh-DB-safe check in this project, "table doesn't exist yet" and "table has 0 rows" are both treated as "not bootstrapped yet."

`conform.py` exposes `health_check() -> list[Check]` the same way connectors do, checked directly in `doctor.py` (not through the connector loop, since it isn't a connector) — see ADR-013.

Team identity is resolved the same way player identity is — by ID, not by name, wherever a source actually provides one. `core.team.mlb_team_id` is derived from already-resolved `core.game` rows (self-bootstrapping majority vote over `raw.mlb_schedule`'s own numeric team IDs, `_backfill_mlb_team_id`), then used to fix the `core.game` rows the original city+nickname string match missed (`_backfill_team_ids_via_mlb_id`) — no name reconciliation involved. `core.team_alias` is the fallback only for sources with no numeric ID scheme at all (Polymarket, Kalshi), and deliberately stays a small, source-verified seed list (`_TEAM_ALIAS_SEED` in `conform.py`), not an attempt to reconcile every source's naming in general. See ADR-029.

## Loading patterns

Four loading patterns cover every connector so far — pick the one that matches the source's shape, don't invent a fifth without a real need:

1. **CSV text + COPY, hand-written raw table** (`chadwick_register`) — for sources that already hand you well-formed CSV text. Column list for the `COPY` is derived from the CSV's own header row, not hardcoded. Table schema is a real migration, since there are few enough tables to hand-author.
2. **DataFrame + `load_dataframe()`, full reload** (`lahman`) — for sources you'd rather not hand-write ~20+ table schemas for; `load_dataframe` derives the table's DDL from the DataFrame's own columns (`CREATE TABLE IF NOT EXISTS`), then `TRUNCATE`s and reloads. Right for sources small enough, or snapshot-shaped enough, that reloading the whole table every run is cheap and correct.
3. **DataFrame + `load_dataframe(..., scope_column=, scope_value=)`, partitioned reload** (`retrosheet`) — for sources landed in independent chunks (one season, one date range) where a full reload on every run would be wasteful and would also wipe out every other already-loaded chunk. Replaces only rows matching `scope_value`, leaving the rest of the table alone. Each chunk's load is independently idempotent — re-running for one season/date range doesn't touch any other. `scope_column` doesn't have to be a single natural field: if more than one independent source can land rows for the same obvious key (e.g. a regular-season game and a post-season game from the same year both have `_season = "2024"`), scope on a synthesized composite instead (`retrosheet_event`/`retrosheet_box` use `_scope = f"{season}_{group}"`) — scoping on season alone in that situation means a later load's replace silently deletes an earlier one's rows first. Found in production, expensively — see ADR-010. Note this is "chunk replaces chunk," not literal insert-only — a re-run for the same chunk still deletes-then-reinserts it.
4. **DataFrame + `append_dataframe()`, pure insert, no replace** (`mlb_api`'s live-game capture) — for genuinely append-only event-stream data with no natural "chunk" to replace: every previous call's rows stay meaningful, not just the latest (e.g. a live-game snapshot captured repeatedly through a game — the whole point is keeping every snapshot for a time series, not overwriting with the newest one). Shares `load_dataframe`'s table-creation/schema-drift-tolerance logic (`_ensure_table_and_columns`) but never truncates or deletes. See ADR-015.

### Download step

Every connector that fetches over HTTP (all of the above except `chadwick_register`, which reads a git-cloned CSV directly) downloads to disk first via `mlb_baseball/manifest.py`'s `download()`, before any parsing happens — see ADR-008. A file already on disk with a matching hash isn't re-fetched; `download(..., force=True)` bypasses that for archives a source updates in place (the current season/decade). Parsing and loading stay fused in one step (no separate on-disk "parsed" artifact) — only the network fetch was the fragile, expensive part worth making independently resumable; re-parsing an already-downloaded file is cheap.

### External tool dependencies

Some connectors don't just need Python packages — `retrosheet_event`/`retrosheet_box` shell out to the Chadwick Baseball Bureau's `cwevent`/`cwgame`/`cwbox` CLI tools (`mlb_baseball/chadwick_tools.py`), which have to be installed as system binaries (see README.md "Requirements"). Any connector with a dependency like this must expose it as a `mlb doctor` check (`chadwick_tools.missing_tools()` via `shutil.which`) so a missing dependency is caught up front, not partway through a multi-hour bootstrap as a bare `FileNotFoundError` — see ADR-011.

## Configuration

Secrets (including `DATABASE_URL`, `TEST_DATABASE_URL`, and API keys) stay in
environment variables documented in `.env.example`; no credentials or
connection strings are committed. Optional local `mlb.toml`, copied from
`mlb.toml.example`, holds only ordinary operational overrides: download/log
directories and the already-existing bounded MLB API analytics controls.
Environment variables take precedence over TOML, then documented built-in
defaults apply. `mlb preflight` resolves and validates these settings without
network ingestion or PostgreSQL writes, checks dependencies and free disk, and
prints the exact next commands. It is the required first step for a new clone.

## Scheduling

Two cadences, not one — see ADR-016 and ADR-023:

- **Every 5 minutes — `mlb_api` only.** `scripts/mlb_api_update.sh` runs `mlb ingest mlb_api --mode update`, guarded with `flock`, logging to `logs/mlb_api_update.log` (gitignored). This is the one genuinely time-sensitive job: live in-progress game state and the current day's schedule/standings. `mlb_api.health_check()` uses `check_recent_run` (not just `check_last_run`) so `mlb doctor` catches the scheduler having silently stopped, not just the last run having failed.
- **Once a day — every connector.** `scripts/mlb_daily_update.sh` runs `mlb update` (every registered connector's `update()`, same `flock` + logging shape, logs to `logs/mlb_daily_update.log`). Every connector's `update()` is deliberately scoped to be cheap — current season only, or a small full-catalog re-check, never a full historical re-fetch (see each connector's `bootstrap()`/`update()` split, e.g. `statcast.py`, `bref.py`, `statcast_leaderboard.py`) — so running all of them daily is safe. This is what keeps Statcast leaderboards, Baseball-Reference season stats, and Retrosheet's current-decade archive from going stale as a season progresses, without re-running the connector's `bootstrap()`.

Neither script is installed to crontab automatically — see the "Bootstrap procedure" section below and CLAUDE.md's action-confirmation rules; a person (or agent, with explicit confirmation) adds the crontab line.

`mlb_api`'s reference/personnel/organizational data (ADR-020 — coaches, alumni, personnel, attendance, stat leaders, etc.) is a deliberate third case: it lives in `bootstrap()`, not `update()`, and isn't scheduled at all. Re-running ~30 teams' worth of these lookups on any automated cadence (even daily) would be pure API/DB load for data that doesn't meaningfully change day-to-day. Refresh it by re-running `mlb ingest mlb_api --mode bootstrap` manually, occasionally (e.g. once a season, or when you notice something stale) — an operator decision, not a cron job.

## Bootstrap procedure

`mlb bootstrap` runs every registered connector's `bootstrap()` in one command — see `mlb_baseball/cli.py`'s `_run_all`. The supported clean-clone path is `mlb preflight`, then `mlb migrate` to create schemas, keys, and indexes, then `mlb bootstrap`, `mlb doctor`, `mlb conform` once required raw checks are healthy, and finally `mlb inventory`. See the README's "Setup" section for exact commands.

A few things worth knowing before running it for real, not after:

- **Run expensive MLB API work in its explicit stage, not as one opaque serial loop.** `mlb ingest mlb_api --stage analytics --start-year 1950 --end-year <year> --workers 16` archives and loads bounded parallel game batches with per-item resume state. The 16-worker setting won the current-source benchmark; the bound remains explicit so the free API is not hammered. The rest of a full database bootstrap can still take substantial time because of Statcast and historical reference calls, but an analytics retry is no longer expected to repeat completed games or wait on unrelated endpoint families.
- **It's resumable, not restart-from-zero.** Every connector's `bootstrap()` skips already-loaded seasons (`season_already_loaded`) before doing any network work, so killing a bootstrap run (or it failing partway through) and re-running `mlb bootstrap` picks up roughly where it left off instead of re-downloading everything. This is also why stale-run cleanup matters if you do kill a run mid-flight — see ADR-022.
- **A failure in one connector doesn't block the rest.** `mlb bootstrap` logs and continues past any connector whose `bootstrap()` raises, then exits non-zero at the end if anything failed — check the output for `FAILED` lines rather than assuming a non-zero exit means nothing loaded.
- **`lahman` prefers a manually-downloaded zip** (see `docs/DATA_SOURCES.md`) but falls back to a pinned network mirror automatically if none is found in `downloads/` — `mlb bootstrap` will not stop and wait for one.
- **`retrosheet_event` and `retrosheet_box` need `cwevent`/`cwgame`/`cwbox` on `PATH`** (see README "Requirements") — `mlb doctor` checks for these and tells you if they're missing, but `mlb bootstrap` itself will just fail those two connectors and continue.
- Run `mlb doctor` after a bootstrap (full or partial) to confirm what actually landed — every connector's `health_check()` reports on its own tables, so a clean `mlb doctor` run is the real "is this database usable yet" signal, not just "did the command exit 0."

## Orchestration and future boundary decisions

- Workflow orchestration: Cron plus `flock` and source advisory locks remain sufficient for current scheduled jobs; complex workflow engines (Airflow/Dagster) remain unnecessary unless coordination demands exceed script capabilities.
- Feature store and modeling platform: Governed by `AGENTS.md`, `plans/03-research-statistics-and-features.md`, and `plans/04-modeling-simulation-and-experiments.md`.
- Public serving layer: `serve` schema and Astro site contracts are deferred to `plans/05-serving-astro-and-launch.md`; public serving remains read-only and rights-gated.
