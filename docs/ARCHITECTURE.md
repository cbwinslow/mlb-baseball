# Architecture

Scope: Phase 1 (data ingestion) only. Modeling and website architecture will get their own sections here once those phases start — don't design them prematurely (see [NORTH_STAR.md](NORTH_STAR.md)).

## Database

Single Postgres instance, addressed via `DATABASE_URL` in `.env` (see [DECISIONS.md](DECISIONS.md) ADR-002). No assumption about how Postgres is hosted — bare-metal is the expected default, nothing requires Docker.

## Layered schema (Medallion-style)

- **Raw / landing** — source-faithful tables, one per upstream source, append-only. What actually came back from Retrosheet/MLB Stats API/Statcast/etc., minimally reshaped. This is what makes re-runs safe: if a transform has a bug, raw data doesn't need to be re-fetched to fix it.
- **Conformed** — cleaned, typed, deduplicated, joined against the Chadwick ID crosswalk so every player/team reference is consistent across sources. This is the layer modeling (Phase 2) and the website (Phase 3) are expected to consume — not raw.

Nothing beyond these two layers is being designed yet. If a third layer turns out to be needed once modeling starts, add it then.

## Connector shape

Each source in [DATA_SOURCES.md](DATA_SOURCES.md) gets one connector responsible for: fetching, landing into its raw table, and being safely re-runnable (idempotent — re-running a connector for a date range that's already loaded doesn't duplicate rows). Connectors are independent of each other; the Chadwick ID crosswalk is the thing that ties their outputs together, not the connectors themselves.

## Configuration

All configuration (database connection, any API keys for Kalshi, etc.) goes through environment variables documented in `.env.example`. No credentials or connection strings committed to the repo.

## Explicitly not designed yet

- Orchestration/scheduling (cron vs. a workflow tool) — decide once there's more than one connector and a real need for scheduling, not before.
- Any modeling or feature-store layer.
- Any website/API-serving layer.
