# Public Python API

`mlb-baseball` helps researchers bootstrap a **database they own**. It does
not host data, expose a public query API, or create a database automatically.

The supported import surface is deliberately small and exported from
`mlb_baseball`:

| API | Purpose |
|---|---|
| `configure()` | Set process-local `DATABASE_URL` and data-rights profile. No connection or write occurs. |
| `migrate_database()` | Apply package migrations to the configured local database. |
| `ingest_source()` | Run one registered connector after profile validation. |
| `conform_database()` | Build canonical `core` relations from landed `raw` data. |
| `build_features()` | Rebuild point-in-time `gold.game_feature` rows. |
| `run_predictions()` | Run the feature stage and append prediction snapshots. |
| `get_connection()` | Obtain a normal psycopg connection for researcher SQL. |
| `inventory_tables()` / `inventory_runs()` | Inspect landed relations and recent connector runs. |
| `health_checks()` | Run read-only operational health checks. |

Everything else is implementation detail, including connector modules, loaders,
advisory-lock functions, and individual conformance builders. Their imports
are not compatibility promises.

## Local bootstrap example

Create and operate your own PostgreSQL database outside this package, then:

```python
import mlb_baseball as mlb

mlb.configure(
    database_url="postgresql:///my_mlb_research",
    profile="public_safe",
)
mlb.migrate_database()

# The profile is fail-closed. Retrosheet-family sources are currently allowed
# in public_safe; local_research is for owner-controlled research only.
mlb.ingest_source("retrosheet_reference", mode="bootstrap")
mlb.ingest_source("retrosheet_gamelog", mode="bootstrap")
mlb.conform_database()
mlb.build_features()

with mlb.get_connection() as conn, conn.cursor() as cur:
    cur.execute("SELECT count(*) FROM core.game")
    print(cur.fetchone())
```

`migrate_database()`, `ingest_source()`, `conform_database()`, `build_features()`,
and `run_predictions()` write only
to the configured database. Test against a disposable database first. Never
point them at someone else's or a shared production database without an
approved run plan.

## Data rights and reproducibility

Choose a source profile deliberately:

- `public_safe` is conservative and currently Retrosheet-family only.
- `licensed_full` is no broader until a documented license exists.
- `local_research` is the default for owner-controlled research and is not a
  public-display permission.

See [SOURCE_RIGHTS.md](SOURCE_RIGHTS.md), [TABLE_CONTRACTS.md](TABLE_CONTRACTS.md),
and [SQL_OWNERSHIP.md](SQL_OWNERSHIP.md) before publishing derived work.
