# SQLMesh Transforms DOX

## Purpose

Own deterministic, set-based SQLMesh transformations and audits that turn stable
raw/core facts into governed research/gold products.

## Ownership

This subtree owns SQLMesh model files, model metadata, audits/tests, and promotion
logic for transformations that are clearer and more reproducible as named SQL
models than embedded Python SQL.

## Local Contracts

- SQLMesh is the selected transformation framework. Do not introduce dbt as a
  parallel transform runtime.
- Move logic here incrementally only after exact parity/tie-out against the
  existing authoritative implementation.
- SQLMesh is appropriate for deterministic relational transforms, rolling
  statistics, research marts, feature-family tables, evaluation marts, and future
  serving marts.
- Keep procedural identity reconciliation, network ingestion, file parsing,
  sequential algorithms, model training, and simulation in Python unless a
  measured refactor proves otherwise.
- Every model must make grain, key, event time, cutoff/availability time, source
  lineage, incremental strategy, and null semantics understandable.
- Never compute a rate by averaging lower-grain rates when aggregate
  numerators/denominators are available.
- Point-in-time models must use only information available at the declared cutoff.
- Avoid duplicate formulas across SQLMesh and Python. If two implementations are
  needed, name one canonical definition and add parity tests.
- Historical immutable periods should not be recomputed unnecessarily. Prefer
  incremental models with explicit lookback/backfill behavior where correct.
- Public-facing/redistributable models must enforce source profile/rights rules;
  SQLMesh lineage does not by itself grant redistribution rights.

## Work Guidance

Before adding or changing a model:

1. identify the authoritative upstream relations and their grains;
2. verify the formula/relationship and point-in-time semantics;
3. define expected row identity and null/coverage behavior;
4. add SQLMesh audits/tests that catch duplicate keys, impossible values, and
   missing required inputs;
5. tie out against the prior implementation or an external reference before
   promotion.

Keep models focused. Prefer reusable narrow domain relations over one ever-wider
`game_feature` table.

## Verification

Run the current SQLMesh plan/test workflow for the affected model/environment plus
SQLFluff and relevant PostgreSQL integration/tie-out tests. Never promote a model
to production based only on SQL compilation.

Representative checks include:

```bash
uv run sqlfluff lint transforms
uv run pytest tests/integration -q
```

Use the repository's current SQLMesh command/environment documented in
`docs/SQLMESH_OPERATIONS.md`; do not guess production promotion commands.

## Child DOX Index

No child DOX files initially. Add a domain child only when a group of models has a
stable distinct contract (for example batting/pitching research marts), not for
every SQL file.
