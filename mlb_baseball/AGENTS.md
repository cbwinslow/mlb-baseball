# MLB Python package DOX

## Purpose

This subtree owns the importable Python package for acquisition, conformance, database access, research/statistics logic, exports, CLI orchestration, and model/research utilities.

Read the repository-root `AGENTS.md` first. This file specializes those project-wide rules for `mlb_baseball/**` and routes work to deeper DOX contracts where they exist.

## Ownership

- Package/public API and import boundaries.
- Runtime configuration, database access, ingestion orchestration, health checks, exports, research access, and command implementation.
- Source-specific acquisition under `connectors/`.
- Operational SQL resources under `sql/` when present.
- Modeling/research code under `model/` while that boundary exists.
- Large legacy gravity-well modules such as `cli.py` and `conform.py` remain supported facades during staged decomposition; do not rewrite them wholesale.

## Local Contracts

- PostgreSQL remains the authoritative system of record. Package code must preserve the `raw` / `core` / `gold` / `meta` layering and explicit data grains.
- Prefer small cohesive modules, typed public contracts, `Protocol`/dataclass/enum constructs where they solve a current interoperability problem, and plain functions where they are simpler.
- Do not create speculative inheritance/plugin frameworks. Existing registries and explicit dispatch are preferred until measured requirements justify a framework.
- Keep dependency direction clean: low-level/pure statistics and domain logic must not depend on reporting, CLI, or heavyweight ML/runtime initialization.
- Public behavior should be backward-compatible unless the change deliberately updates callers, tests, CLI/docs, and migration notes together.
- SQL ownership follows `docs/SQL_OWNERSHIP.md`: derived set-based relations belong in SQLMesh, DDL in numbered migrations, operational SQL in named package resources when it is too substantial to remain inline.
- Source-faithful raw data must remain source-faithful. Normalize/reconcile meaning in `core`/conformance, not by silently rewriting raw source facts.
- Point-in-time and availability semantics are part of correctness. Never introduce future leakage for convenience.
- Measure before performance rewrites. GPU/vectorization/JIT/parallelism must have a demonstrated workload and benchmark.

## Progressive Context Workflow

Before changing a file in this subtree:

1. Read root `AGENTS.md`.
2. Read this file.
3. Read any deeper `AGENTS.md` on the path to the target.
4. If a matching `<filename>.dox.md` exists, read it before editing the source file.
5. Read the tests and authoritative docs named by the nearest DOX contract.
6. Load a skill/runbook only when the task actually requires that procedure.

After a meaningful behavioral or ownership change, update the nearest applicable DOX contract/sidecar in the same change.

## Work Guidance

- Prefer reuse/consolidation over adding near-duplicate helpers.
- Preserve stable facades while decomposing large modules incrementally.
- New modules should have one clear reason to exist and an obvious owner/consumer relationship.
- Do not move formulas between Python and SQL without identifying one canonical definition and parity tests when both implementations must exist.
- Keep error paths explicit. Ingestion/source failures must remain visible and tracked.
- When behavior can be validated with pure tests, keep it pure. Database behavior should be tested against real PostgreSQL rather than mocked transaction semantics.

## Verification

Use the narrowest relevant tests first, then the repository quality gates appropriate to the change. Typical package changes may require:

- `uv run pytest tests/unit/...`
- `uv run pytest tests/integration/...`
- `uv run ruff check .`
- `uv run mypy mlb_baseball`
- SQLFluff / SQLMesh validation when SQL changes.

Never claim these passed unless they were actually run in the current environment/session.

## File-Level DOX Profiles

A file-level sidecar is appropriate when a module has substantial hidden contracts, historical quirks, cross-subsystem dependencies, or decomposition risk. It is not required for every small ordinary module.

Initial high-value profiles:

- `cli.py.dox.md`
- `conform.py.dox.md`
- connector sidecars declared by `connectors/AGENTS.md`

## Child DOX Index

| Child | Scope |
| --- | --- |
| [`connectors/AGENTS.md`](connectors/AGENTS.md) | External source acquisition, source rights/provenance, replay, idempotency, health, and connector-level file DOX. |
| [`sql/AGENTS.md`](sql/AGENTS.md) | Operational package SQL ownership and verification. |
| [`model/AGENTS.md`](model/AGENTS.md) | Modeling/PIT/evaluation contracts while this package remains a durable boundary. |

Other package directories inherit this contract until they demonstrate stable, distinct rules that justify their own child DOX.