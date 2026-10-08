# Bootstrap runbook

This is the supported path for recreating a researcher-owned MLB database.
It uses PostgreSQL as the system of record and leaves production choices to the
researcher. It does not require Docker, R, baseballr, or machine presets.

## 1. Configure a database

Create two PostgreSQL databases yourself: one research database and one
separate disposable test database. Clone this repository, then copy
`.env.example` to `.env` and set only the connection values you use:

```bash
DATABASE_URL=postgresql://user:password@host:5432/my_mlb_research
TEST_DATABASE_URL=postgresql://user:password@host:5432/my_mlb_test
```

Keep credentials in `.env`, your shell, or a secret manager. Use the optional
`mlb.toml` only for ordinary overrides such as download/log paths, historical
analytics range, retries, request timeout, and worker count. Environment
variables override that file. Do not point `TEST_DATABASE_URL` at the research
database.

Install the project and the Chadwick command-line tools required for the
Retrosheet event/box sources. `mlb preflight` reports missing tools with their
names before a long run begins.

## 2. Preview, migrate, and land raw sources

```bash
uv sync --extra dev
uv run mlb preflight --with-conform
uv run mlb migrate
uv run mlb bootstrap --profile local_research
uv run mlb doctor
uv run mlb inventory
```

`preflight` never downloads or writes. It checks the database connection,
writable directories, required Chadwick tools, and prints the planned commands.
`migrate` is serialised and records each numbered migration. `bootstrap` runs
all registered sources; it records every source run and continues with other
sources if one fails, then exits nonzero so the failure is visible.

To retry only a failed source, use its exact command, for example:

```bash
uv run mlb ingest mlb_api --mode bootstrap --profile local_research
```

Download manifests, checksums, and run records make supported connectors safe
to resume and rerun. Do not truncate raw tables to retry a failure. Use
`mlb status --run-status`, `mlb doctor`, and `mlb inventory` to identify the
source and table that need attention. For a long MLB API historical run, use
`mlb metrics --source mlb_api --window-minutes 5` to distinguish upstream/API
time from database work.

### Find what is left to ingest

`mlb coverage` is the "what should we hold versus what do we hold" report. It
is read-only (it runs in a `READ ONLY` transaction and cannot write). For every
source and raw table it prints the unit (season, game, date, market, file), the
expected count and where that expectation comes from, the held count, anything
accounted for as a recorded source gap (a `meta.ingestion_item` row with status
`unavailable`), the missing units, and the exact `mlb ingest ...` command that
closes the gap. A table with no derivable expectation prints
`no expectation defined: <reason>`.

```bash
uv run mlb coverage                                  # every source
uv run mlb coverage --source mlb_api --table mlb_win_prob
uv run mlb coverage --json                           # stable, sorted keys, no timestamps
uv run mlb coverage --markdown
```

The loop is: run `mlb coverage`, run the printed fix command (every fix is an
idempotent `mlb ingest` that skips what is already loaded), run `mlb coverage`
again. A fix entry that carries a `note:` line cannot fully repair the gap with
the existing command; read the note first. The registry of expectations is
`mlb_baseball/coverage/registry.py`; its contract is in
`mlb_baseball/coverage/AGENTS.md`.

If `mlb doctor` reports an active `workflow lock`, another raw ingestion,
conformance, or model operation owns the database workflow. Wait for it to
finish; do not start a competing command or kill a session unless its owner
has explicitly confirmed it is stale.

## 3. Conform and prove the result

Only run conformance after the raw checks needed for your selected sources are
healthy:

```bash
uv run mlb conform
uv run mlb audit
uv run mlb audit --scope statcast
uv run mlb audit --scope database
```

`conform` rebuilds canonical `core` relations from preserved raw data. It is
idempotent: repeat runs rebuild the same canonical facts rather than appending
duplicates. `audit` is read-only. Treat `FAIL` as a stop condition; investigate
each `WARN` using its supplied count and sample identifiers. Expected provider
history and unresolved crosswalks are retained and documented rather than
silently guessed or deleted.

## 4. Verify the installation and changes

Run tests only against the disposable test database:

```bash
TEST_DATABASE_URL=postgresql://user:password@host:5432/my_mlb_test uv run pytest
uv run ruff check .
uv run mypy mlb_baseball
```

For the project-maintained representative proof, see
[Conformance rehearsal](CONFORMANCE_REHEARSAL.md). It copies a bounded sample
from a source database through a read-only connection and writes only to
`mlb_test`; it is not a production migration procedure.

## AI-agent checklist

1. Confirm `DATABASE_URL` is the intended researcher database and
   `TEST_DATABASE_URL` is distinct before any destructive test operation.
2. Run `preflight`; resolve failed checks before migration or download.
3. Run migration, raw bootstrap, doctor, and inventory in that order.
4. Retry only failed connectors; preserve artifacts and raw rows for diagnosis.
5. Run conform, then the game, Statcast, and database audits.
6. Report row counts, source-run outcomes, failures, warnings, and exact sample
   identifiers. Never guess an identity or modify production without explicit
   owner approval.

The supported configuration contract is deliberately small. If an environment
needs different capacity or retention choices, the operator supplies those
values through PostgreSQL and the existing `.env`/`mlb.toml` overrides rather
than selecting a project-defined machine profile.

## Optional PostgreSQL extensions (ADR-302)

The database works on a stock PostgreSQL 16 server; extra extensions are a bonus.
To get the full toolbox on a Debian/Ubuntu PGDG server:

```bash
scripts/pg_extensions_install.sh --preload   # apt packages + preload list (no restart)
sudo systemctl restart postgresql@16-main    # activates pg_stat_kcache / pg_qualstats
psql -d mlb -f migrations/0116_postgres_extensions.sql   # idempotent; or `mlb migrate` on a new DB
mlb doctor                                   # "optional extensions" shows what is present
```

Migration 0116 skips any extension whose package is missing, so a server without
them still migrates. `pg_duckdb`, `pgvectorscale`, `pgai`, `pg_graphql`,
`pgml` and `multicorn2` have no PGDG package and are not included (ADR-302).

`pg_search` (ParadeDB `.deb` release) and `pg_duckdb` (source build) are not in apt.
Install them by hand before running the preload step; `pg_duckdb`:
`git clone --branch v1.1.1 --recurse-submodules https://github.com/duckdb/pg_duckdb.git`,
then `make -j8 PG_CONFIG=/usr/lib/postgresql/16/bin/pg_config && sudo make install PG_CONFIG=...`
(needs `libcurl4-openssl-dev`, `postgresql-server-dev-16`).

`scripts/pg_extensions_github.sh` installs everything else that has no apt package
(pgvectorscale, pg_graphql, pg_column_tetris, multicorn2, tbls, pgEdge MCP server,
postgres_dba, Atlas, the postgresai and azimutt CLIs, pgai). Not installed on the shared
cluster: `pg_vectorize` (needs pgmq + a moved `cron.database_name`) and PostgresML
`pgml` (no PG16/Ubuntu 24.04 package, Python ML stack in the server process); both
belong on a separate throwaway cluster if wanted (ADR-302).
