# Migrations DOX

## Purpose

Own forward schema evolution for PostgreSQL: schemas, tables, views, indexes,
constraints, roles, extensions, comments, and durable metadata contracts.

## Ownership

Numbered migration files are the authoritative ordered DDL history. Runtime code
must not silently create a parallel schema-management system.

## Local Contracts

- Migrations are forward, ordered, reviewable changes. Do not edit old applied
  migrations to rewrite history unless the repository's migration runner
  explicitly treats them as unapplied development-only files.
- Production PostgreSQL is authoritative. Never run a destructive migration
  without making the target database explicit first.
- Tests must exercise migrations against the isolated disposable pytest database,
  never production.
- Keep schema layers `raw`, `core`, `gold`, `meta`, and future `serve` consistent
  with the root architecture contract.
- Table/relation changes must state grain, key/identity, time semantics, lineage,
  null policy where important, update strategy, and rights/profile implications.
- New extensions require a measured current need and an architecture/operations
  review; do not add database extensions because they are interesting.
- Prefer constraints that encode real invariants. Do not add uniqueness/FK/check
  constraints until historical/current data has been audited for the claimed
  invariant.
- Indexes require an actual query/workload rationale. Use `EXPLAIN`/measurement;
  do not add speculative indexes to every foreign key or timestamp.
- Preserve point-in-time correctness: schema convenience must not collapse
  observation time, event time, or forecast cutoff into one ambiguous timestamp.
- Rights/public-safety metadata must fail closed when a new relation can mix
  restricted/local-only sources.

## Work Guidance

Before adding a migration:

1. search existing migrations for the relation/index/constraint;
2. inspect current table contracts and affected code/models;
3. choose the smallest forward change;
4. update living table/data-dictionary docs when the public research contract
   changes;
5. add regression/integration coverage for constraints or migration behavior that
   can fail only in PostgreSQL.

Large set-based derived logic generally belongs in SQLMesh models, not migration
DDL. Migrations create durable structures; transforms populate/derive research
products.

## Verification

At minimum for relevant changes:

```bash
uv run pytest tests/integration -q
uv run sqlfluff lint migrations
```

Also run the repository migration/clean-bootstrap path when the change affects
fresh-database creation, extension setup, partitioning, roles, or migration order.
Use `EXPLAIN (ANALYZE, BUFFERS)` or equivalent evidence for performance-driven
index changes where practical.

## Child DOX Index

No child DOX files. Individual numbered migration sidecars are intentionally not
required; relation-level durable truth belongs in table/stat registries and
living docs, while migration files remain historical DDL evidence.
