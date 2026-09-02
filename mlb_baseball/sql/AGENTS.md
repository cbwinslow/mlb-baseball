# Package SQL resource DOX

## Purpose

This directory owns named SQL statements that are executed by Python package code but are too substantial, reusable, or important to remain embedded as inline strings. It is distinct from SQLMesh transformation models and numbered migrations.

## Ownership

Use this directory for:

- operational/select/update statements owned by a Python module;
- conformance statements invoked procedurally by `conform.py` or extracted successors;
- reconciliation/health/tie-out queries reused by package code;
- package queries whose lifecycle is coupled to a Python API rather than a standalone SQLMesh model.

Do **not** put here:

- schema/role/extension DDL -> `migrations/`;
- durable derived warehouse/research relations better expressed as SQLMesh models -> `transforms/`;
- ad-hoc analyst queries with no supported package caller -> docs/notebooks/research artifacts as appropriate.

## Local Contracts

- Every SQL resource should have an identifiable Python owner/caller. Search for `read_sql("<filename>")` before changing or deleting it.
- Keep SQL schema-qualified for project relations where ambiguity matters.
- Preserve the owning module's grain, key, null, point-in-time, and source-rights contracts.
- Do not duplicate a business/statistical formula independently across multiple SQL files or Python. Name one canonical implementation and add parity tests if two forms are genuinely required.
- Parameterize runtime values through the caller/psycopg mechanisms; do not construct unsafe SQL by interpolating user/source strings.
- Be aware of psycopg placeholder semantics and `%` characters in SQL/comments. The owning caller/test should prove the resource executes through the real driver path.
- Source-faithful/raw values should not be normalized here unless the owning conformance contract explicitly assigns that normalization to this query.
- Point-in-time market/feature queries must use event/availability/observed timestamps explicitly; current-state shortcuts are not equivalent.

## Relationship to SQLMesh

Prefer SQLMesh when the SQL defines a named derived relation with lineage, incremental semantics, audits, or research/serving materialization value.

Keep package SQL here when execution is inherently part of procedural orchestration/identity reconciliation or when it is a focused read/update statement rather than a warehouse model.

When moving a resource into SQLMesh:

1. identify the old Python caller;
2. prove output parity on representative data;
3. move formula ownership/documentation;
4. remove the obsolete resource/call only after callers/tests are migrated.

## Work Guidance

- Favor clear CTEs and explicit names over compact clever SQL.
- Document source-specific marker/null semantics in the owning sidecar/module when they are non-obvious.
- Review query plans before adding performance-driven indexes or denormalization.
- Do not hide a large data migration in an ordinary operational query.

## Verification

For changed resources:

- run the owning unit/integration tests through psycopg;
- run SQLFluff according to repository configuration;
- verify row grain/key uniqueness where joins changed;
- run conformance/health tie-outs when a conformance resource changes;
- run PIT/leakage regression tests when timestamp predicates change.

## File-Level DOX

Ordinary `.sql` resources do not need one sidecar each. Their local meaning should be discoverable from the filename, owning Python module/sidecar, tests, and SQL comments. Add a SQL-specific sidecar only when a resource has an unusually complex independent contract.

## Child DOX Index

No child directories currently.
