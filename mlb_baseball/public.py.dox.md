# `public.py` DOX

## Purpose

Own the package's current small supported **operational/programmatic API** for researchers who control their own PostgreSQL database. It wraps package operations; it is not an ORM, hosted service, or the future ergonomic research-query facade.

## Ownership

Supported exports currently include:

- `configure()`
- `migrate_database()`
- `ingest_source()`
- `conform_database()`
- `build_features()`
- `run_predictions()`
- `health_checks()`
- `inventory_tables()`
- `inventory_runs()`
- `get_connection`
- `IngestMode` / source-profile error surface.

`__all__` is part of the intended supported surface. Review it with every public API change.

## Scope / Non-Goals

This module currently exposes **operations**, not high-level research questions. It should stay stable while the project separately introduces a researcher-facing `ResearchDB` facade such as player/stat/coverage/leader queries.

Do not overload `public.py` with hundreds of ad-hoc query helpers. A future research facade should be a deliberately designed API layered over stable core/gold relations and stat/coverage metadata.

Do not introduce a second ORM. Researchers should continue to be able to use psycopg/pandas/Polars/Arrow directly against their owned database.

## Configuration Contract

`configure()` only mutates process-local environment variables:

- optional `DATABASE_URL`;
- optional `MLB_DATA_PROFILE`.

It does not connect, create, migrate, or write data by itself.

- Reject empty database URLs.
- Validate source-profile names against the canonical profile registry.
- Do not hide global/process-local side effects: callers choosing `configure()` are opting into environment-backed configuration used by existing package modules.

## Ingestion Contract

`ingest_source()`:

- source must exist in `registry.CONNECTORS`;
- active/explicit source profile is checked before connector execution;
- supports `bootstrap` and `update` for all standard connectors;
- `backfill` is capability-checked (`backfill_history`) and should fail clearly when unsupported;
- returns the connector's table -> row-count mapping.

Do not bypass source-rights/profile checks for programmatic callers. The Python API must not be a loophole around CLI policy.

## Database Operation Contract

- `migrate_database()` delegates to the canonical migration runner.
- `conform_database()` delegates to `conform.run()` and inherits its full rebuild/prerequisite semantics.
- `build_features()` / `run_predictions()` delegate to the current model facade; future restructuring should preserve this API or provide an intentional compatibility/deprecation path.
- `health_checks()` is read-only; state-changing repair remains an explicit operation elsewhere.
- inventory helpers expose live operational metadata rather than caching another state model.

## Dependency Direction

This module should remain a thin facade over supported package APIs.

- Do not move domain logic here.
- Do not import `cli.py` to reuse command behavior; CLI and programmatic API should call common underlying modules.
- Keep heavyweight/optional model imports from making research-only operation APIs unnecessarily expensive as dependency extras are later split; refactor carefully because current top-level imports are observable.

## Future `ResearchDB` Relationship

Planned direction:

```python
from mlb_baseball import ResearchDB

db = ResearchDB.connect()
db.players.search("Aaron Judge")
db.batting.season(...)
db.stats.describe("woba")
db.coverage("woba")
```

That future API should complement, not silently replace, the operational functions here:

- `public.py` / operational facade: build/maintain/inspect a local database;
- `ResearchDB`: query/use the research database ergonomically.

Do not implement the future facade until research grains/stat registry/coverage contracts are stable enough to support it.

## Work Guidance

- Treat function names/arguments/return shapes as supported API.
- Prefer additive changes over silent behavior changes.
- New operations should wrap a stable package capability that users genuinely need programmatically, not mirror every CLI command.
- Keep source-profile enforcement and errors consistent with CLI behavior without duplicating policy logic.

## Verification

For changes:

- unit tests for configuration/validation/dispatch behavior;
- source-profile tests;
- integration tests for migration/conform/inventory wrappers where behavior changes;
- import/public-surface tests for `__all__` and top-level package exposure;
- docs/examples if supported Python usage changes.

## Child DOX Index

No child DOX files.
