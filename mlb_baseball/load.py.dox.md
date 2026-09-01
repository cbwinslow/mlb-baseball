# load.py DOX

## Purpose

Own generic DataFrame-to-PostgreSQL raw loading semantics shared by pandas-shaped
connectors: identifier sanitization, dynamic raw table/column creation, schema
drift policy, scoped replacement, bulk scope replacement, and append-only event
loading.

## Ownership

Source implementation: `load.py`.

Primary integration contract: `tests/integration/test_load_dataframe.py`.
Connector integration tests exercise this module through production-shaped loads.

## Raw Schema Contract

This loader is intentionally flexible because many source-owned raw schemas are
large and change over time.

- Source columns are sanitized mechanically to PostgreSQL-safe identifiers; this
  must not become semantic renaming of source vocabulary.
- Source columns are generally landed as `text`; typed canonical interpretation
  belongs in core/gold unless a project-owned metadata field has an explicit
  stronger contract elsewhere.
- `_loaded_at` is project-owned load metadata and is created automatically.
- If a later source batch adds a column, the raw table may gain that column.
- Missing columns in a particular batch may be legitimate source sparsity and are
  controlled by `schema_drift_policy` (`ignore`, `warn`, `error`).
- Sanitized source column collisions are fatal. Never silently choose one of two
  source fields that normalize to the same PostgreSQL name.

## Replacement Modes

### `load_dataframe()`

- With no scope: whole-table `TRUNCATE` then load. Use only for snapshot sources
  whose whole dataset is the replacement unit.
- With `scope_column`/`scope_value`: delete and replace exactly one independent
  source scope. The loader creates an index on the scope column because historical
  production loads proved unindexed scoped deletes become prohibitively slow.

### `replace_dataframe_scopes()`

Bulk equivalent for several independent scopes in one delete/copy operation.
Callers must include every successfully fetched scope, including an empty scope
that should remove stale prior rows.

### `append_dataframe()`

Use for observations/events that remain meaningful historically (live-game
captures, market snapshots, etc.). Append identity/conflict semantics must
preserve old observations rather than turning an event stream into "latest only."

Do not choose a load mode by convenience; choose it from the source's actual
snapshot/chunk/event semantics.

## COPY and Performance Contract

`_copy_dataframe()` currently materializes the DataFrame as CSV text then streams
that text through psycopg COPY. It is simple and correct but can materialize a
large in-memory string.

Do not replace it on intuition. Benchmark representative large sources first;
possible future paths include chunked/streaming COPY or Arrow/Polars, but any
change must preserve null/text/quoting behavior and connector tests.

## Transaction Contract

This module does not own high-level commit cadence; callers decide when a source
scope/year/game is durable. Loader functions participate in the caller's
connection/transaction and must leave failures visible for caller rollback.

Do not insert hidden commits that would break connector failure isolation.

## Schema Drift Doctrine

Drift warnings/errors are an observation and review mechanism, not proof that the
source is wrong. Some Retrosheet early-season products legitimately have fewer
columns. Other connectors may require `error` when a stable modern API unexpectedly
changes shape.

The connector sidecar owns the appropriate policy for its source.

## Verification

Run:

```bash
uv run pytest tests/integration/test_load_dataframe.py -q
uv run ruff check mlb_baseball/load.py tests/integration/test_load_dataframe.py
uv run mypy mlb_baseball/load.py
```

When changing shared loading behavior, also run representative connector tests for
at least one whole-table source, one season/chunk-scoped source, one multi-scope
source, and one append-only source.
