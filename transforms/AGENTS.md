# SQLMesh transform DOX

## Purpose

This subtree owns deterministic, set-based derived relations managed by SQLMesh. It is the preferred home for reproducible `gold`/future `serve` transformations that are clearer and safer as declarative SQL than procedural Python.

## Ownership

- SQLMesh models, audits, tests, environments, and incremental transformation definitions.
- Analysis-ready relations derived from already-landed/conformed data.
- Reusable research/statistical relations whose formula ownership has been explicitly assigned to SQL.

This subtree does not own network ingestion, source parsing, procedural identity reconciliation, model training, or schema/role DDL.

## Local Contracts

- SQLMesh is the sole transformation framework for this repository. Do not add dbt alongside it without a recorded architecture decision.
- Every model must have an explicit grain and stable key semantics.
- Incremental models must define the time/key window precisely and must not silently recompute immutable history when a bounded update is sufficient.
- Point-in-time correctness and availability semantics are part of the model contract; no future leakage.
- Do not duplicate a formula independently in SQL and Python. One implementation is canonical; parity tests are required when two implementations are necessary.
- Missing measurements stay missing unless the statistical/data contract explicitly defines zero or another imputation.
- Models must preserve rights/profile constraints of upstream data and must not create a redistribution loophole by joining restricted inputs into a supposedly public relation.
- Identity reconciliation that depends on procedural evidence ordering belongs in Python conformance, not SQLMesh merely for stylistic consistency.
- DDL belongs in `migrations/`, not hidden in transformation models.
- Model names, schema placement, and materialization should reflect current repository conventions rather than inventing a parallel warehouse vocabulary.

## Work Guidance

- Prefer small composable models with explicit dependencies over one enormous query.
- Tie new/reworked models to atomic facts first; season/career aggregates should aggregate stable grains rather than average already-aggregated rates.
- For pitching innings, use outs as the canonical additive quantity where applicable; display innings can be derived later.
- Add audits for grain uniqueness, required relationships, domain bounds, freshness/coverage, and leakage-relevant invariants where useful.
- Compare production/current outputs before replacing an existing Python or SQL relation.
- Optimize only after measuring representative SQL plans/runtime.

## Verification

For changed transforms, normally verify:

- SQLMesh parse/plan for the affected environment;
- model-specific audits/tests;
- tie-out against the prior canonical relation or trusted fixture when replacing logic;
- SQLFluff;
- relevant integration/research tests;
- explicit checks of grain/key uniqueness and point-in-time behavior.

Do not claim production parity without an actual tie-out.

## Child DOX Index

Add child DOX only when the transform tree develops durable domain boundaries (for example batting, pitching, market, or serving marts) with materially distinct local contracts. Avoid creating one instruction file per model.
