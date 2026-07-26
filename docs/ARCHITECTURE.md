# Architecture

Scope: Phase 1 (data ingestion) only. Modeling and website architecture will get their own sections here once those phases start — don't design them prematurely (see [NORTH_STAR.md](NORTH_STAR.md)).

## Database

Single Postgres instance, addressed via `DATABASE_URL` in `.env` (see [DECISIONS.md](DECISIONS.md) ADR-002). No assumption about how Postgres is hosted — bare-metal is the expected default, nothing requires Docker.

## Layered schema (Medallion-style)

- **`raw`** — source-faithful tables, one per upstream source, minimally reshaped, deliberately untyped (`text` columns, no PK/FK/constraints — see `mlb_baseball/load.py`). Event-stream sources (Retrosheet, Statcast, MLB Stats API) land append-only; snapshot sources (the Chadwick register) truncate-and-reload each run instead, since there's no meaningful "new rows since last time" for a full-snapshot source (see Connector contract below). Staying untyped is what lets raw tolerate schema drift from a source without breaking (e.g. `load_dataframe`'s `ALTER TABLE ADD COLUMN` for a later batch with columns an earlier one didn't have) — raw data doesn't need to be re-fetched just because a downstream transform has a bug.
- **`core`** — real relational structure: surrogate primary keys, foreign keys, indices. Built by joining already-landed `raw` tables against the Chadwick ID crosswalk so every player/team/game reference is consistent across sources — Kimball's "conformed dimensions," which is where the schema's original name (`conformed`, renamed to `core` — see ADR-013) came from. `core.player`/`core.team`/`core.game` are the first tables here. This is the layer modeling (Phase 2) and the website (Phase 3) are expected to consume — not raw.
- **`gold`** — schema exists (`migrations/0004_core_gold_schemas.sql`), deliberately holds no tables yet. Reserved for ML-feature/serving-shaped tables once Phase 2/3 actually need them — see ADR-013. Don't design tables here speculatively.

`core` is populated by `mlb_baseball/conform.py` (`mlb conform`), not a connector — see "Conform contract" below.

## Connector contract

This project is a reusable ingestion toolkit, not a one-shot script — the goal is that a stranger can clone the repo, bootstrap the full database from nothing, and keep it updated afterward, the same way `pybaseball` gives reusable access to Statcast/FanGraphs/Bref. Every source in [DATA_SOURCES.md](DATA_SOURCES.md) gets a connector module under `mlb_baseball/connectors/` that exposes exactly two functions, both returning `dict[str, int]` of `{table: row_count}`:

- **`bootstrap()`** — full historical load, from nothing. What a new user runs once.
- **`update()`** — incremental: pull what's new since the last run. What gets run on a schedule for maintenance.

For sources distributed as a full snapshot (e.g. the Chadwick register), `bootstrap()` and `update()` are legitimately the same operation — both do a full truncate-and-reload. For sources with real incremental structure (Statcast, MLB Stats API), they differ: `update()` should only pull the recent window, not replay history.

Every run — from either function — is wrapped in `mlb_baseball.ingest.track_run()`, which logs to `meta.ingestion_run` (source, mode, status, row counts, errors, timestamps). This is what makes bootstrapping and maintenance observable instead of a black box: `SELECT * FROM meta.ingestion_run ORDER BY started_at DESC` shows what ran and whether it worked.

Every connector also exposes a third function: **`health_check() -> list[Check]`**, using the shared helpers in `mlb_baseball/health.py`. This is what `mlb doctor` calls to answer "is everything actually working?" in one command — see CLAUDE.md "Operational health checks". Not optional: `tests/unit/test_cli_registry.py::test_all_connectors_expose_health_check` enforces it.

Connectors are independent of each other; the Chadwick ID crosswalk is what ties their outputs together during conforming, not the connectors themselves. All of them are driven through one CLI registered in `mlb_baseball/cli.py` — not separate one-off scripts per source:

- `mlb ingest <source> --mode bootstrap|update` — run a connector
- `mlb conform` — rebuild `core` from already-ingested `raw` data (see "Conform contract" below)
- `mlb inventory` — live table/row-count report plus last run per source, queried fresh every time (a static doc would go stale immediately with this many tables)
- `mlb doctor` — DB connectivity, schema/migration state, and every connector's `health_check()` in one pass

## Conform contract

`mlb_baseball/conform.py` builds `core` from `raw` — a transform, not a connector: it never touches the network, has no `bootstrap()`/`update()` split, and isn't in `mlb_baseball/registry.py`'s `CONNECTORS` (so it doesn't show up under `mlb ingest <source>`; it's its own `mlb conform` subcommand). One `run()` entry point does a full truncate-and-rebuild every time — simplest-correct at `core`'s current row count (~225K games), matching CLAUDE.md's "prefer explicit, boring code" guidance over a more complex incremental-diff approach.

Before rebuilding, `run()` checks that the `raw` tables it depends on actually have data (`_check_prerequisites()`), raising an actionable error (naming the `mlb ingest ... --mode bootstrap` command to fix it) rather than either running silently on empty raw tables or failing mid-join with a confusing error. Like every other fresh-DB-safe check in this project, "table doesn't exist yet" and "table has 0 rows" are both treated as "not bootstrapped yet."

`conform.py` exposes `health_check() -> list[Check]` the same way connectors do, checked directly in `doctor.py` (not through the connector loop, since it isn't a connector) — see ADR-013.

## Loading patterns

Three patterns cover every connector so far — pick the one that matches the source's shape, don't invent a fourth without a real need:

1. **CSV text + COPY, hand-written raw table** (`chadwick_register`) — for sources that already hand you well-formed CSV text. Column list for the `COPY` is derived from the CSV's own header row, not hardcoded. Table schema is a real migration, since there are few enough tables to hand-author.
2. **DataFrame + `load_dataframe()`, full reload** (`lahman`) — for sources you'd rather not hand-write ~20+ table schemas for; `load_dataframe` derives the table's DDL from the DataFrame's own columns (`CREATE TABLE IF NOT EXISTS`), then `TRUNCATE`s and reloads. Right for sources small enough, or snapshot-shaped enough, that reloading the whole table every run is cheap and correct.
3. **DataFrame + `load_dataframe(..., scope_column=, scope_value=)`, partitioned reload** (`retrosheet`) — for sources landed in independent chunks (one season, one date range) where a full reload on every run would be wasteful and would also wipe out every other already-loaded chunk. Replaces only rows matching `scope_value`, leaving the rest of the table alone. Each chunk's load is independently idempotent — re-running for one season/date range doesn't touch any other. `scope_column` doesn't have to be a single natural field: if more than one independent source can land rows for the same obvious key (e.g. a regular-season game and a post-season game from the same year both have `_season = "2024"`), scope on a synthesized composite instead (`retrosheet_event`/`retrosheet_box` use `_scope = f"{season}_{group}"`) — scoping on season alone in that situation means a later load's replace silently deletes an earlier one's rows first. Found in production, expensively — see ADR-010.

### Download step

Every connector that fetches over HTTP (all of the above except `chadwick_register`, which reads a git-cloned CSV directly) downloads to disk first via `mlb_baseball/manifest.py`'s `download()`, before any parsing happens — see ADR-008. A file already on disk with a matching hash isn't re-fetched; `download(..., force=True)` bypasses that for archives a source updates in place (the current season/decade). Parsing and loading stay fused in one step (no separate on-disk "parsed" artifact) — only the network fetch was the fragile, expensive part worth making independently resumable; re-parsing an already-downloaded file is cheap.

### External tool dependencies

Some connectors don't just need Python packages — `retrosheet_event`/`retrosheet_box` shell out to the Chadwick Baseball Bureau's `cwevent`/`cwgame`/`cwbox` CLI tools (`mlb_baseball/chadwick_tools.py`), which have to be installed as system binaries (see README.md "Requirements"). Any connector with a dependency like this must expose it as a `mlb doctor` check (`chadwick_tools.missing_tools()` via `shutil.which`) so a missing dependency is caught up front, not partway through a multi-hour bootstrap as a bare `FileNotFoundError` — see ADR-011.

## Configuration

All configuration (database connection, any API keys for Kalshi, etc.) goes through environment variables documented in `.env.example`. No credentials or connection strings committed to the repo.

## Explicitly not designed yet

- Orchestration/scheduling (cron vs. a workflow tool) — decide once there's more than one connector and a real need for scheduling, not before.
- Any modeling or feature-store layer.
- Any website/API-serving layer.
