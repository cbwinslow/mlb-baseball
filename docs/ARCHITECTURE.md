# Architecture

Scope: Phase 1 (data ingestion) only. Modeling and website architecture will get their own sections here once those phases start — don't design them prematurely (see [NORTH_STAR.md](NORTH_STAR.md)).

## Database

Single Postgres instance, addressed via `DATABASE_URL` in `.env` (see [DECISIONS.md](DECISIONS.md) ADR-002). No assumption about how Postgres is hosted — bare-metal is the expected default, nothing requires Docker.

## Layered schema (Medallion-style)

- **Raw / landing** — source-faithful tables, one per upstream source, minimally reshaped. Event-stream sources (Retrosheet, Statcast, MLB Stats API) land append-only; snapshot sources (the Chadwick register) truncate-and-reload each run instead, since there's no meaningful "new rows since last time" for a full-snapshot source (see Connector contract below). Either way, raw data doesn't need to be re-fetched just because a downstream transform has a bug.
- **Conformed** — cleaned, typed, deduplicated, joined against the Chadwick ID crosswalk so every player/team reference is consistent across sources. This is the layer modeling (Phase 2) and the website (Phase 3) are expected to consume — not raw.

Nothing beyond these two layers is being designed yet. If a third layer turns out to be needed once modeling starts, add it then.

## Connector contract

This project is a reusable ingestion toolkit, not a one-shot script — the goal is that a stranger can clone the repo, bootstrap the full database from nothing, and keep it updated afterward, the same way `pybaseball` gives reusable access to Statcast/FanGraphs/Bref. Every source in [DATA_SOURCES.md](DATA_SOURCES.md) gets a connector module under `mlb_baseball/connectors/` that exposes exactly two functions, both returning `dict[str, int]` of `{table: row_count}`:

- **`bootstrap()`** — full historical load, from nothing. What a new user runs once.
- **`update()`** — incremental: pull what's new since the last run. What gets run on a schedule for maintenance.

For sources distributed as a full snapshot (e.g. the Chadwick register), `bootstrap()` and `update()` are legitimately the same operation — both do a full truncate-and-reload. For sources with real incremental structure (Statcast, MLB Stats API), they differ: `update()` should only pull the recent window, not replay history.

Every run — from either function — is wrapped in `mlb_baseball.ingest.track_run()`, which logs to `meta.ingestion_run` (source, mode, status, row counts, errors, timestamps). This is what makes bootstrapping and maintenance observable instead of a black box: `SELECT * FROM meta.ingestion_run ORDER BY started_at DESC` shows what ran and whether it worked.

Connectors are independent of each other; the Chadwick ID crosswalk is what ties their outputs together during conforming, not the connectors themselves. All of them are driven through one CLI (`mlb ingest <source> --mode bootstrap|update`) registered in `mlb_baseball/cli.py` — not separate one-off scripts per source.

## Configuration

All configuration (database connection, any API keys for Kalshi, etc.) goes through environment variables documented in `.env.example`. No credentials or connection strings committed to the repo.

## Explicitly not designed yet

- Orchestration/scheduling (cron vs. a workflow tool) — decide once there's more than one connector and a real need for scheduling, not before.
- Any modeling or feature-store layer.
- Any website/API-serving layer.
