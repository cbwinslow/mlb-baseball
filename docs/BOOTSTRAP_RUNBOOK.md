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
Retrosheet event/box sources. `mlb doctor` reports missing tools with their
names before a long run begins.

## 2. Preview, migrate, and land raw sources

```bash
uv sync
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
