# MLB project DOX contract

This file is the root contract and routing index for agents working in this
repository. It intentionally contains only project-wide rules and pointers to
more specific context. Detailed subsystem rules belong in the nearest applicable
child `AGENTS.md`; file-specific durable contracts may live in adjacent
`<source>.dox.md` files when a child declares a file-documented DOX profile.

Before editing any path:

1. read this file;
2. walk from the repository root toward every target path;
3. read every `AGENTS.md` on that path;
4. if the nearest contract requires a matching `.dox.md` sidecar, read it;
5. follow links to exact runbooks, tests, ADRs, registries, or reference docs only
   when they are relevant to the task.

This is progressive disclosure: the repository may contain a large amount of
useful durable context, but each task should load only the context it needs.

## Mission and current focus

The current product focus is a free, reproducible MLB research database and
research toolkit. Prediction/modeling and the Astro consumer site remain later
layers and must not pull work ahead of research-database usability.

The platform should ultimately support three connected layers:

1. trustworthy historical/current baseball data with stable identities,
   provenance, rights, and explicit grains;
2. reproducible research statistics, features, simulation, and modeling; and
3. a transparent forecasting/market-value product that separates model
   probability, market probability, uncertainty, and betting-value claims.

Read `docs/NORTH_STAR.md`, `docs/PRODUCT_DIRECTION.md`, `docs/ARCHITECTURE.md`,
`docs/MAP.md`, and the active plan before broadening scope.

## Global invariants

### PostgreSQL is authoritative

PostgreSQL remains the system of record. Preserve the existing schema layers:

- `raw`: source-faithful, replayable landing data and immutable/source snapshots;
- `core`: conformed identities and canonical facts at explicit grains;
- `gold`: validated research/statistics/features/evaluation products;
- `meta`: ingestion, source, transformation, research, feature, experiment,
  artifact, and model provenance;
- `serve`: only when a narrow read-only public contract is ready.

Do not rename or replace these foundational layers for stylistic reasons.

### Production data safety

Never let tests or exploratory verification mutate the production database.
`DATABASE_URL` may point at real data. Destructive commands must make their
intended target obvious before execution.

Pytest currently creates a unique disposable database per pytest process through
`pytest-postgresql`, using `TEST_DATABASE_URL` only as the base connection/default.
Do not reintroduce a shared mutable `mlb_test` working database. The authoritative
local test contract lives in `tests/AGENTS.md` and `tests/conftest.py`.

### Research truth, provenance, and rights

- Preserve source-faithful raw data and canonical identity evidence.
- Prefer honest `NULL`/unknown over invented reconciliation.
- Every derived public result must be explainable from source, formula/version,
  grain, coverage, and validation evidence.
- Source rights are enforced, not merely documented. `public_safe` remains
  fail-closed. Read `docs/SOURCE_RIGHTS.md` before changing redistribution rules.
- Point-in-time claims must reflect what was knowable at the stated cutoff.
  Future leakage is never acceptable as a convenience.
- Never claim betting value without time-stamped permitted market observations,
  vig-aware evaluation, calibration, and uncertainty.

### Preserve and consolidate before adding architecture

Prefer existing assets, libraries, tables, helpers, workflows, and docs over
creating parallel systems. Before introducing a framework or abstraction, show a
real current requirement it solves and why the existing solution is insufficient.

- SQLMesh is the selected SQL transformation framework; do not add dbt beside it.
- PostgreSQL remains authoritative; ClickHouse is only a measured future option.
- Do not create speculative plugin frameworks, ORM layers, or orchestration
  systems when explicit mappings and current workflows are sufficient.
- Measure before proposing rewrites, vectorization, GPU work, new indexes, or
  database-engine changes.

### Stable contracts over accidental coupling

- Use typed, composable Python interfaces where a current reuse boundary exists.
- Prefer `Protocol`, `StrEnum`, frozen/slotted dataclasses, and small pure
  functions when they clarify real domain contracts; do not force abstraction
  for its own sake.
- Keep deterministic transforms/statistics deterministic. AI agents may research,
  review, propose, explain, and triage; they do not become the source of truth for
  stored gold statistics or probabilities.
- Never duplicate a business formula across Python and SQL without an explicit
  canonical definition and parity tests.

## Verification doctrine

Every meaningful change must be verified at the layer where it can actually fail.

- pure logic: deterministic unit tests;
- database behavior: real PostgreSQL integration tests;
- CLI behavior: CLI-dispatch tests through real argparse;
- formula/stat changes: hand-calculated fixtures and credible external tie-outs
  where available;
- SQL: SQLFluff plus relation/grain/tie-out tests;
- source connectors: idempotency, error/retry behavior, health checks, and
  production-shaped load tests with network I/O mocked/captured, not DB behavior;
- performance work: representative measurement before and after.

Use the exact local verification commands from the nearest child DOX rather than
remembered commands from old plans.

## Planning, delegation, and parallel work

- Preserve user changes and parallel-agent work; never assume a dirty worktree is
  disposable.
- Bounded delegated tasks must state exact scope, edit authority, applicable plan,
  safety constraints, verification expectations, and required handoff.
- Delegated agents must not merge, delete worktrees, rewrite unrelated changes,
  alter production data, or silently expand into the next work package.
- Re-read and verify delegated diffs yourself before treating them as complete.
- Work in focused branches and PRs; direct pushes to protected `main` are not the
  normal path.

## Agent-specific context is first class

The DOX tree contains shared repository truth. It does **not** erase native
agent/harness instructions.

- `CLAUDE.md`, nested `CLAUDE.md`, `.claude/rules/`, Claude skills, hooks, and MCP
  instructions may contain genuine Claude-specific behavior that differs from
  other agents.
- Codex natively consumes the applicable `AGENTS.md` hierarchy; do not create a
  duplicate full `CODEX.md` unless a concrete Codex-specific requirement appears.
- Gemini/Agy may use `GEMINI.md`, configured `AGENTS.md` loading, and bounded
  delegation prompts for Gemini-specific behavior.
- Agent Zero may use the full DOX pattern directly.

Shared facts should not be independently copied into every vendor file. Native
agent files may import/link shared DOX and then add their own behavior.

## DOX update contract

After a meaningful change, perform a DOX pass before closing the task.

Update the nearest owning `AGENTS.md` or required `.dox.md` when the change alters
any durable:

- purpose, responsibility, or ownership boundary;
- public/local interface or command contract;
- required input/output, grain, key, time semantics, or side effect;
- source/rights/provenance behavior;
- safety or permissions rule;
- verification procedure;
- dependency direction;
- child/index structure.

Do not churn DOX for internal refactors that preserve every documented contract.
Delete stale statements instead of appending contradictory history. Dated history
belongs in plans/ADRs/progress records, not operating contracts.

## Definition of done

A change is not complete until:

- applicable tests/checks pass or limitations are explicitly reported;
- docs/registries/contracts change with behavior when required;
- point-in-time, source-rights, and grain semantics remain explicit;
- no unrelated parallel work was overwritten;
- the applicable DOX chain and sidecars were re-checked for drift.

## Child DOX Index

| Child | Scope |
| --- | --- |
| [.github/AGENTS.md](.github/AGENTS.md) | CI, security automation, dependency/release workflows, templates. |
| [docs/AGENTS.md](docs/AGENTS.md) | Living docs, dated evidence, ADR/reference/runbook ownership and navigation. |
| [migrations/AGENTS.md](migrations/AGENTS.md) | Forward schema evolution, DDL safety, extensions, DB contract changes. |
| [mlb_baseball/AGENTS.md](mlb_baseball/AGENTS.md) | Python package architecture and child package routing. |
| [plans/AGENTS.md](plans/AGENTS.md) | Active execution plans and progress/evidence records. |
| [scripts/AGENTS.md](scripts/AGENTS.md) | Operational shell/Python scripts and destructive-operation safeguards. |
| [tests/AGENTS.md](tests/AGENTS.md) | Pytest isolation, unit/integration boundaries, fixtures, real-Postgres verification. |
| [transforms/AGENTS.md](transforms/AGENTS.md) | SQLMesh models, audits, incremental transforms, promotion/tie-out rules. |

Additional child boundaries should be added only when they represent durable
ownership or workflow, not merely because a directory exists.
