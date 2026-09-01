# User manual — the MLB research database

Hands-on guide for someone standing up this database and querying it. It
covers ingestion, conformance, the derived `gold` layer, health checks, and
getting data out. Every command shown is a real `mlb` subcommand — run
`mlb <command> --help` for its full options.

The prediction ladder (Elo / GBM / Markov) and the Astro website are separate,
currently-paused efforts. This manual does not cover them; see
`docs/PRODUCT_DIRECTION.md` for their status.

---

## 1. Architecture & data flow

```
[ Sources: Retrosheet · Statcast · MLB StatsAPI · Baseball-Reference ·
           Lahman · Chadwick register · Kalshi · Polymarket ]
                    │
                    ▼   mlb ingest / bootstrap / update   (atomic download + load)
           raw.*     — source-faithful, untyped, one table per source
                    │
                    ▼   mlb conform                       (ID-based entity resolution)
           core.*    — relational: player, team, venue, game, play, pitch, market
                    │
                    ▼   mlb report  +  the enrichment SQL  (derived, point-in-time-safe)
           gold.*    — game_feature (~80 pregame features), player_season,
                       team_season, division_standing, game_export (wide view)
                    │
                    ▼   psql / any client  ·  mlb export
           CSV · Excel · Parquet · direct SQL
```

Schema layering is documented in `docs/ARCHITECTURE.md`; per-table grain and
keys in `docs/TABLE_CONTRACTS.md`; every column in `docs/DATA_DICTIONARY.md`.

---

## 2. First-time setup

See the top-level `README.md` "Setup" for the full clean-clone sequence. The
short version, against a Postgres database you control:

```bash
uv sync --extra dev
cp .env.example .env          # set DATABASE_URL to your Postgres instance
uv run mlb preflight --with-conform   # validates config, tools, DB — no writes
uv run mlb migrate            # apply the schema
uv run mlb bootstrap          # ingest every registered source (slow — resumable)
uv run mlb doctor             # confirm the raw layer and dependencies are healthy
uv run mlb conform            # build core.* from raw.*
uv run mlb report             # build the gold.* season marts
```

`cwevent` / `cwgame` / `cwbox` (Chadwick tools) must be on `PATH` for the
Retrosheet event and box-score connectors — `README.md` "Requirements" has the
build steps. `mlb doctor` tells you if they are missing.

To ingest one source at a time (useful while setting up, or to retry a single
failed source):

```bash
uv run mlb ingest <source> --mode bootstrap    # sources listed in mlb_baseball/registry.py
```

### Data-rights profile

`MLB_DATA_PROFILE` gates which sources ingestion will touch:

| Profile | Sources | Use |
|---|---|---|
| `local_research` (default) | all | your own research on your own machine |
| `public_safe` | Retrosheet only | anything you intend to redistribute or publish |

`public_safe` is deliberately small and fail-closed. See
`docs/SOURCE_RIGHTS.md`.

---

## 3. Keeping it current

Two cron jobs (see `README.md` "Scheduling"):

```cron
*/5 * * * * /path/to/mlb-baseball/scripts/mlb_api_update.sh   # live season state
0 6 * * *   /path/to/mlb-baseball/scripts/mlb_daily_update.sh  # mlb update, once daily
```

`mlb update` runs every connector's cheap incremental refresh (current season
or a small catalog check — never a full historical re-fetch). Follow a data
refresh with `mlb conform` and `mlb report` to propagate it into `core` and
`gold`.

Re-running any ingestion step is idempotent — running it twice does not
duplicate or corrupt rows.

---

## 4. Inspecting the database

| Command | Shows |
|---|---|
| `mlb doctor` | one-pass health: DB connectivity, schema, migrations, per-connector checks |
| `mlb inventory` | live row-count estimates and last-run status per source (`--exact`, `--partitions`) |
| `mlb status` | table-by-table population as a progress-bar view (`--all`, `--watch N`, `--run-status`) |
| `mlb schema` | schema object / constraint catalogue (`--partitions`) |
| `mlb field-census` | raw→core→gold field lineage inventory (`--exact`, `--output-json`, `--output-markdown`) |
| `mlb metrics` | Postgres + ingestion snapshot: cache use, table size, dead rows, throughput |
| `mlb audit` | read-only data-correctness gate — run after ingestion and after conform (`--scope game/database/statcast`) |
| `mlb player-id <system> <id>` | given one ID (e.g. `mlbam 660271`), resolve the same player's IDs across Retrosheet / MLBAM / BBRef / FanGraphs / Chadwick |

---

## 5. Querying

The database is plain PostgreSQL — connect with `psql`, DBeaver, R's `DBI`,
Python's `psycopg` / SQLAlchemy, or anything else that speaks Postgres.

Start from the documented `gold` relations rather than assembling from `raw`:

- `gold.game_export` — one wide row per game: readable team and starter names,
  the real final score, and the pregame feature columns.
- `gold.player_season` — batting and pitching season lines plus WAR.
- `gold.team_season` — team season stats and advanced metrics.
- `gold.division_standing` — season-end division standings.

`docs/RESEARCH_QUERY_RUNBOOK.md` has example queries and the guardrails for
point-in-time correctness (the season marts are final-season values, not
pregame inputs).

---

## 6. Exporting to a file

Direct from `psql` today, per `docs/RESEARCH_QUERY_RUNBOOK.md`:

```bash
psql "$DATABASE_URL" -c "\copy (SELECT * FROM gold.game_export WHERE season = 2024) TO 'games_2024.csv' WITH CSV HEADER"
```

A dedicated `mlb export` command — any allow-listed relation to CSV / Excel /
Parquet, plus a rights-filtered `public_safe` bundle for redistribution — is
in progress. See
`docs/superpowers/specs/2026-09-01-research-database-v1-design.md`. This
section will be filled in when it lands.

---

## 7. Backups

```bash
uv run mlb backup                 # pg_dump the whole database (plain SQL), with rotation
uv run mlb backup --schema-only   # structure only
uv run mlb restore <file> --yes   # DESTRUCTIVE — overwrites the target database
```

`mlb restore` targets whatever `DATABASE_URL` points at. Be certain which
database that is before running it.

---

## 8. Programmatic use

`mlb_baseball` exposes a small supported Python API for bootstrapping and
querying a database you own — `configure`, `migrate_database`, `ingest_source`,
`conform_database`, `get_connection`, and a few more. It does not host data or
expose a public query endpoint. See `docs/PUBLIC_API.md`.
