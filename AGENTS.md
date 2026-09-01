# MLB Baseball — root DOX contract

This is the **small, always-relevant project contract and filesystem context map**.
Do not treat it as an encyclopedia. Before editing a path, follow the applicable
`AGENTS.md` chain into that subtree and read a matching `<source>.dox.md` sidecar
when one exists.

Agent/harness-specific files such as `CLAUDE.md` may add real tool-specific
workflow requirements. They supplement this shared project truth; they do not
replace or weaken it.

## Mission and current focus

Build a trustworthy, reproducible MLB research database and toolkit from multiple
lawfully usable sources, with strong identity reconciliation, provenance,
point-in-time semantics, reusable statistics, and portable research outputs.

Current priority order:

1. reliable ingestion, source identity, rights, provenance, and health;
2. coherent atomic research grains and validated statistics;
3. researcher-facing query/export ergonomics;
4. forecasting/model experimentation only after the research-data contract is
   stable enough to support it;
5. consumer odds/analytics product work after the research/forecasting evidence
   is ready.

Do not reopen model/website expansion merely because older plans contain it.
Use `docs/MAP.md`, `plans/README.md`, and the newest active owner-approved plan to
resolve current priority.

## Global invariants

### PostgreSQL and data safety

- PostgreSQL is the authoritative system of record.
- Preserve the `raw` / `core` / `gold` / `meta` layering unless a recorded
  architecture decision changes it.
- Production data is real. Never run destructive SQL, restore, migration, or
  repair work against an ambiguous database target.
- Pytest database mechanics are owned by `tests/AGENTS.md` and
  `tests/conftest.py`; do not copy remembered test-database assumptions into
  root instructions.

### Source truth, rights, and provenance

- Raw data remains source-faithful; normalize/reconcile meaning downstream.
- Preserve source URL/artifact identity, retrieval/provenance metadata, parser
  version, coverage limitations, and rights/profile constraints where the
  owning subsystem requires them.
- A technically accessible source is not automatically redistributable.
  Rights/profile enforcement is a correctness requirement, not only a doc note.
- Missing measurement is not zero. Do not fabricate coverage or silently fill
  uncertain identities/values merely to increase completeness.

### Point-in-time honesty

- Event time, observation time, availability time, and forecast cutoff are
  distinct concepts when the data requires them.
- Never use future/post-outcome information in a historical feature, market
  probability, model input, or evaluation sample that claims pre-event validity.
- When a trustworthy identity or pre-event observation cannot be resolved, an
  honest `NULL`/missing result is preferred to a guess.

### Architecture and reuse

- Reuse/consolidate existing project assets and established libraries before
  creating parallel frameworks or duplicate helpers.
- SQLMesh is the transformation framework. Do not add dbt beside it without a
  recorded decision based on a measured unmet requirement.
- Preserve stable public/CLI/facade behavior while decomposing large modules
  incrementally.
- Use typed interfaces, `Protocol`, dataclasses, enums, or abstraction layers
  when they solve a current interoperability/ownership problem—not as decoration
  or preparation for hypothetical future plugins.
- Measure before optimization, vectorization, GPU/JIT/parallelization, or rewrite
  proposals. Prefer the smallest proven fix.
- Keep project-owned names short (normally one or two words) where practical;
  source-faithful raw names may preserve established upstream vocabulary.

### Statistical/research truth

- Calculated statistics/features require a clear definition, grain, inputs,
  null policy, time/PIT semantics, citation/rationale, and verification.
- Prefer atomic additive facts as the basis for season/career rollups rather than
  averaging already-aggregated rates.
- Retain negative/failed research evidence when it prevents repeated rediscovery.
- Predictive claims require chronological/forward evidence and probability
  quality/calibration—not accuracy alone. Detailed rules live in
  `mlb_baseball/model/AGENTS.md`.
- Model probability, market probability, fair price, expected value, and a
  recommendation/pick are separate concepts.

## Progressive context workflow

Before changing a file:

1. Read this root contract.
2. Walk from repository root to the target and read every applicable child
   `AGENTS.md`.
3. Read the matching `<filename>.dox.md` if the target has one.
4. Read only the exact tests, ADRs, source docs, table/stat contracts, or other
   references named by that local context and needed for the task.
5. Load a skill/runbook only when its procedure is actually required.
6. For agent-specific behavior, also follow that agent's native local context
   (`CLAUDE.md`, `GEMINI.md`, path rules, skills, etc.) where present.

After a meaningful change, update the **nearest owning** DOX/context artifact when
its durable contract, ownership, verification, or child index changed. Do not
copy the same rule into every ancestor.

## Work and verification doctrine

- Read the implementation and nearest tests before editing.
- Separate observed facts from recommendations; verify uncertain claims against
  code/data/library behavior rather than memory.
- Tests should exercise the real failure mechanism. Database semantics use real
  PostgreSQL where required; routine source/network tests stay deterministic.
- Update docs, health checks, registries, source rights, table/stat contracts, or
  DOX in the same change when their owned contract changed.
- Never state that tests/lint/type/SQL checks passed unless they actually ran in
  the current execution environment/session.
- A delegated/subagent handoff is evidence, not final verification: inspect the
  diff and re-run the relevant checks before accepting it.

## Git and collaboration safety

- Preserve user and parallel-agent work; never assume an unfamiliar dirty change
  is disposable.
- Work on focused branches/PRs; do not push directly to protected `main`.
- Creating a branch, committing, pushing that branch, and opening an issue/PR in
  this repository is pre-authorized.
- Force-pushing, deleting branches, closing issues, merging PRs, or editing
  another contributor's content requires explicit owner authorization.
- Address substantive human and automated review findings on PRs you are working
  on. Verify each finding; fix real problems and explain concrete false/out-of-
  scope findings rather than silently ignoring them.

## Canonical project map

Start here for deeper shared context:

- `docs/MAP.md` — documentation/navigation map and current focus.
- `docs/NORTH_STAR.md` — durable product/research principles.
- `docs/ARCHITECTURE.md` — data/system architecture.
- `docs/DATA_SOURCES.md` / `docs/SOURCE_RIGHTS.md` — source catalog and rights.
- `docs/SQL_OWNERSHIP.md` — SQL placement/ownership.
- `plans/README.md` — current vs paused/historical execution programs.
- `docs/PROGRESSIVE_CONTEXT_ARCHITECTURE.md` — context/progressive-disclosure design.

## Child DOX Index

| Child | Scope |
| --- | --- |
| [`.github/AGENTS.md`](.github/AGENTS.md) | GitHub Actions, CI/security automation, repository workflow metadata. |
| [`docs/AGENTS.md`](docs/AGENTS.md) | Living docs, ADRs, plans/runbooks, citations, documentation ownership. |
| [`migrations/AGENTS.md`](migrations/AGENTS.md) | PostgreSQL DDL/schema evolution and migration safety. |
| [`mlb_baseball/AGENTS.md`](mlb_baseball/AGENTS.md) | Python package architecture and package-level progressive context. |
| [`plans/AGENTS.md`](plans/AGENTS.md) | Long-horizon/staged execution plans and status semantics. |
| [`scripts/AGENTS.md`](scripts/AGENTS.md) | Operational/maintenance scripts and destructive-operation safety. |
| [`tests/AGENTS.md`](tests/AGENTS.md) | Pytest structure, real PostgreSQL integration, run-specific DB isolation. |
| [`transforms/AGENTS.md`](transforms/AGENTS.md) | SQLMesh models, audits, incrementality, PIT transformation contracts. |

Directories not indexed here inherit this root contract until they develop a
stable, distinct ownership/workflow boundary that justifies a local DOX file.