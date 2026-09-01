# Database migration DOX

## Purpose

This subtree owns ordered PostgreSQL schema evolution: schemas, tables, columns, constraints, indexes, roles, extensions, partitioning, and other DDL that changes the authoritative database structure.

## Ownership

- Numbered forward migrations and their ordering.
- Structural database contracts required by Python, SQLMesh, tests, exports, and research surfaces.
- Extension/index/constraint changes that belong to PostgreSQL itself rather than derived transforms.

Migrations do not own derived research formulas or data-source parsing logic.

## Local Contracts

- PostgreSQL is the system of record. Treat migration correctness as production safety work.
- Before executing any migration manually, make the target database explicit. Production `mlb` is real data; pytest uses run-specific disposable databases under `tests/conftest.py`.
- Migrations are forward-moving. Do not rewrite already-applied migration history merely to make it prettier unless the repository has explicitly established a safe migration-history repair process.
- DDL belongs here rather than embedded in application code.
- Use schema-qualified names for project-owned database objects where ambiguity is possible.
- Preserve source-faithful raw semantics and explicit grain/key contracts when changing raw/core/gold/meta structures.
- Destructive changes require a migration path, impact analysis, and validation of downstream callers/data before removal.
- Extension additions require a real project use case and operational portability consideration; do not accumulate PostgreSQL extensions speculatively.
- Indexes are workload decisions. Prefer evidence from representative queries/`EXPLAIN` over adding indexes by intuition.
- Partitioning changes must preserve query correctness, uniqueness/constraint semantics, ingestion, test setup, and maintenance behavior.
- When schema contracts change, update affected package code, SQLMesh models, tests, table/data docs, exports, and DOX in the same change.

## Work Guidance

- Inspect preceding migrations before choosing numbering/style.
- Make migrations as atomic and restart-safe as PostgreSQL permits.
- Explicitly document non-transactional operations when PostgreSQL requires them.
- Avoid hidden data rewrites inside DDL unless the transformation and runtime cost are understood.
- Prefer constraints that encode real invariants; do not encode uncertain business assumptions as hard constraints.
- For large historical tables, consider lock duration and rewrite behavior before choosing an ALTER pattern.

## Verification

For migration changes, verify on a real disposable PostgreSQL database:

- clean database -> all migrations apply;
- the changed migration creates the intended structure;
- integration tests using affected tables pass;
- relevant SQLMesh models/audits still plan/run when their input schema changed;
- downgrade is not assumed unless explicitly supported.

Also run SQL formatting/lint checks applicable to migration SQL.

## Child DOX Index

No child DOX. Individual migration files normally do not need sidecars because their purpose should be evident from ordered SQL plus referenced ADR/schema docs. Add a sidecar only for an unusually complex migration whose durable operational contract cannot be captured safely in comments/ADR.