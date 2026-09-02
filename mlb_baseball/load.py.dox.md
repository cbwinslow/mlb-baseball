# `load.py` DOX

## Purpose

Own the generic DataFrame-to-PostgreSQL landing primitives used by multiple connectors. This module is a low-level ingestion utility: it creates/extends source-shaped raw tables, enforces column-name safety, supports replace-by-scope and append-only observation semantics, and loads through PostgreSQL `COPY`.

## Ownership

Primary public helpers:

- `load_dataframe()` — full-table replace or one-scope replace.
- `replace_dataframe_scopes()` — bulk replace of multiple independent scopes.
- `append_dataframe()` — append-only event/observation history with declared identity columns.
- `season_already_loaded()` — immutable-past bootstrap optimization for season-scoped APIs.
- schema-drift warning/error types and column-name sanitization helpers.

## Data-Type / Raw-Layer Contract

- Dynamically created raw columns are currently stored as PostgreSQL `text` plus `_loaded_at timestamptz`.
- That is intentional source-landing behavior, not the canonical typed research schema. Strong typing/normalization belongs in migrations/core/gold where the project owns semantics.
- Do not change generic raw values to inferred numeric/date types globally without a source-by-source migration/parity plan; pandas inference and historical source sparsity can be inconsistent.
- Column-name transformation is syntactic only: lowercase/sanitize for PostgreSQL compatibility, not semantic renaming.
- Sanitized column collisions are fatal. Do not silently pick one source column.

## Table/Schema Evolution Contract

- Create a landing table when absent.
- Add newly observed source columns with `ALTER TABLE` so later source batches with legitimate extra fields can land.
- Existing columns absent from a later historical batch are not dropped. Historical source batches may genuinely have fewer fields.
- Schema drift policy is explicit: `ignore`, `warn`, or `error`.
- Connector sidecars own the correct policy for their source; this utility must not assume every source treats drift identically.

## Replace Semantics

### `load_dataframe()`

- Without a scope: `TRUNCATE` then load the complete batch. Use only when the connector truly owns a complete snapshot/full replacement.
- With `scope_column` / `scope_value`: create an index on the scope column if needed, delete only that scope, then `COPY` the replacement rows.
- Scoped replacement is the idempotency primitive for season/file/game chunks; do not replace it with append unless old rows are meant to remain meaningful observations.

The scope index exists because repeated scoped deletes on large raw tables were measured to degrade badly without it.

### `replace_dataframe_scopes()`

- Replaces several successfully fetched independent scopes in one delete/copy operation.
- The caller must include successful empty scopes too so stale rows can be removed when the source legitimately returns no rows.
- Empty bulk replacements still need a known source column shape; do not create schema-less tables.

## Append Semantics

`append_dataframe()` is only for data where every captured observation remains meaningful over time.

- Caller must declare non-empty `identity_columns`.
- Identity columns must exist, be non-null, and be unique within the incoming batch.
- This protects against treating accidental duplicate polls as meaningful history.
- Append does not delete/truncate prior rows.

Use cases include time-stamped live/market observations. If the source concept is "this latest chunk replaces prior rows for this key," use scoped replacement instead.

## COPY Contract / Performance

- `_copy_dataframe()` serializes the incoming DataFrame to CSV text and writes it through psycopg `COPY FROM STDIN`.
- This is already substantially better than row-by-row INSERT for raw ingestion.
- Current implementation materializes the whole CSV string in memory. Treat streaming/chunked COPY as a profiling-driven optimization: benchmark representative large batches before changing this shared path.
- A performance refactor must preserve quoting/null/column order behavior and all connector integration tests.

## SQL Safety

- Table and column identifiers use `psycopg.sql.Identifier`; preserve this.
- Runtime values use parameters.
- Raw source column names can be reserved words; identifiers must remain safely quoted.
- `table` is expected to be schema-qualified in current project usage. Do not introduce untrusted user-selected arbitrary relation names through this low-level API without validation.

## Transaction Contract

This module does not generally commit for callers. Connector/orchestration code owns transaction/commit boundaries so a natural source unit can roll back atomically.

Do not add hidden commits inside loaders; that would break connector failure/retry behavior.

## Dependencies / Consumers

Used heavily by connectors including Retrosheet, MLB API, Lahman/pybaseball-backed sources, market/live snapshot ingestion, and other DataFrame-shaped loaders.

A change here is cross-cutting even if the function edit is small. Search all callers before changing semantics.

## Work Guidance

- Preserve the three distinct storage semantics: full replacement, scoped replacement, append history.
- Do not create a generic ORM/model layer around raw ingestion.
- Keep schema-drift policy caller-controlled.
- Any new convenience API should represent a real fourth storage semantic, not merely rename an existing function.
- If connector-specific transformation is required, keep it in the connector rather than growing source-specific branches here.

## Verification

Run the loader integration tests against real PostgreSQL, especially cases for:

- full replace rerun/idempotency;
- scoped replace preserving other scopes;
- scope-index behavior/contracts;
- schema growth and drift warn/error behavior;
- reserved/sanitized column names and collision errors;
- bulk multi-scope replacement including empty successful scopes;
- append identity validation and preserved historical rows;
- transaction rollback semantics through connector tests.

Then run representative connector integration tests because this module is shared infrastructure.

## Child DOX Index

No child DOX files. This is a leaf shared-infrastructure contract.
