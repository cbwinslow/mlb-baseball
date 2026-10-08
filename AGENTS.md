# MLB Baseball — root DOX contract

> **START HERE: `openspec/project.md`** — the project constitution (product,
> audience, two-product model, current phase, phased ladder, DB standards,
> workflow, CI gates, merge protocol, tooling). Read it before anything else.
> Rationale:
> `docs/superpowers/specs/2026-09-02-project-restructure-design.md`.
>
> **Workflow is OpenSpec** (`/opsx:propose` → `/opsx:apply` → `/opsx:archive`).
> The `plans/` workflow (now `docs/archive/plans/`) and conductor `/spec` are
> retired; `docs/archive/NORTH_STAR.md` is superseded by `openspec/project.md`.
> Superpowers and mattpocock skills are used *inside* a change — see
> **Operating protocol** below.

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

## The two halves of the project

1. **The data platform.** Download, ingest, bootstrap and *maintain* every
   available MLB source in organized PostgreSQL tables, through idempotent,
   re-runnable Python/SQL operations. Anyone (academics, analysts,
   programmers, fans) can download the project and rebuild the same database.
2. **The research and forecasting product built on it.** A cited arsenal of
   sabermetric statistics and point-in-time features, predictive models,
   analysis of Polymarket/Kalshi markets, and published research and
   betting-strategy findings, later a paid subscriber website. We publish
   research; we do not take bets.

**Stages run in this order; finish a stage's gate before pulling the next
forward** (the gates live in `openspec/project.md`):

```text
1 database + ETL + bootstrap + upkeep  ->  2 metrics / features / sabermetrics
  ->  3 predictive models + market research  ->  4 website + paid research
```

Current priority order:

1. reliable ingestion, source identity, rights, provenance, and health;
2. coherent atomic research grains and validated statistics;
3. researcher-facing query/export ergonomics;
4. forecasting/model experimentation only after the research-data contract is
   stable enough to support it;
5. consumer odds/analytics product work after the research/forecasting evidence
   is ready.

Do not reopen model/website expansion merely because older plans contain it.
`openspec/project.md` (constitution) and the `NOW / NEXT / LATER` block in it
resolve current priority; the archived `docs/archive/plans/` tree is history.

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

## Operating protocol — skills, OpenSpec, ADRs, DOX, tools

Do these by default; each names its owner so nothing is restated here.

**Skills (invoke with the Skill tool before acting).**

| Situation | Skill |
| --- | --- |
| Any non-trivial change | OpenSpec: `/opsx:explore` → `/opsx:propose` → `/opsx:apply` → `/opsx:archive` |
| New feature or behavior | `superpowers:brainstorming`, then `superpowers:test-driven-development` |
| Bug, failing test, slow run | `superpowers:systematic-debugging` or `mattpocock-skills:diagnosing-bugs` |
| Stress-testing a plan or decision | `mattpocock-skills:grilling` |
| Domain terms, recording an ADR | `mattpocock-skills:domain-modeling` (our log format is below, not its `docs/adr/`) |
| Module/interface design | `mattpocock-skills:codebase-design` |
| Source/library fact-finding | `mattpocock-skills:research` |
| Editing `AGENTS.md`, `CLAUDE.md`, skills | `mattpocock-skills:writing-for-agents` |
| Before saying "done" or opening a PR | `superpowers:verification-before-completion` |

**ADRs.** A decision that is hard to reverse, surprising without context, and
a real trade-off gets an entry in `docs/DECISIONS.md` (newest first, next
number up) in the same change. The change's `design.md` links the ADR number;
archiving a change that made such a decision without one is incomplete.

**DOX mesh.** Editing a file that has a `<file>.dox.md` sidecar means reading
it first and updating it in the same change when the file's contract,
ownership or verification changed. New subsystem → new local `AGENTS.md` /
sidecar, indexed in the Child DOX Index above.

**Logs.** Operational/infrastructure work gets a dated entry in `changelog/`;
long-running ingestion is observed through `meta.*` run tables and
`mlb doctor`, not by counting rows by hand.

**Tools.** Use the `postgres-mcp` tools for schema inspection and
EXPLAIN/ANALYZE (target database explicit; production `mlb` is read-only
unless the task says otherwise). Use codebase-graph tools for structural
questions before grepping.

**Ingestion standard.** Every source gets an idempotent, resumable Python
operation behind an `mlb` command, with a test that runs it twice and proves
the second run changes nothing, plus a bootstrap path and a `doctor`/health
check for upkeep.

**Documentation is a deliverable.** Keep docs current, accurate and
consolidated: fix or archive a stale doc when you find it, one owner per
fact, link rather than copy.

## Work and verification doctrine

- Fix failures at their originating layer. Do not add a downstream patch or
  widen a health/metric threshold merely to make a check green; a changed
  threshold needs written source/formula/data evidence.
- When a review finds a material gap, give it one durable owner: an existing
  contract/spec, an active OpenSpec change, a named future change behind the
  current phase gate, an executable check, or an explicit archived/rejected
  rationale. Do not leave accepted correctness findings only in chat notes.
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
- AI agents (Claude, Codex, etc.) are pre-authorized to create branches, commit
  changes, push branches, open pull requests, and merge PRs into `main` once CI
  checks (`test`, `secrets`) pass.
- Address substantive human and automated review findings on PRs you are working
  on. Verify each finding; fix real problems and explain concrete false/out-of-
  scope findings rather than silently ignoring them.

## Canonical project map

Start here for deeper shared context:

- `openspec/project.md` — the constitution: product, audience, two-product
  model, current phase, phased ladder, workflow, `NOW / NEXT / LATER` queue.
  Read first.
- `docs/ARCHITECTURE.md` — data/system architecture.
- `docs/DATA_SOURCES.md` / `docs/SOURCE_RIGHTS.md` — source catalog and rights.
- `docs/SQL_OWNERSHIP.md` — SQL placement/ownership.
- `docs/DECISIONS.md` — architecture decision log.
- `docs/archive/` — frozen history (NORTH_STAR, MAP, ROADMAP, plans, reviews);
  see `docs/archive/README.md`.
- `chatgpt/` — point-in-time outside-review evidence. It is not governing
  project truth; read `chatgpt/README.md` for the disposition map and promote
  accepted findings into their canonical owners instead of treating review prose
  as instructions.

## Child DOX Index

| Child | Scope |
| --- | --- |
| [`.github/AGENTS.md`](.github/AGENTS.md) | GitHub Actions, CI/security automation, repository workflow metadata. |
| [`changelog/AGENTS.md`](changelog/AGENTS.md) | Chronological operational changelogs, server administration logs, and milestone audit records. |
| [`docs/AGENTS.md`](docs/AGENTS.md) | Living docs, ADRs, plans/runbooks, citations, documentation ownership. |
| [`migrations/AGENTS.md`](migrations/AGENTS.md) | PostgreSQL DDL/schema evolution and migration safety. |
| [`mlb_baseball/AGENTS.md`](mlb_baseball/AGENTS.md) | Python package architecture and package-level progressive context. |
| [`docs/archive/plans/AGENTS.md`](docs/archive/plans/AGENTS.md) | Long-horizon/staged execution plans and status semantics (archived). |
| [`packages/retrosheetpy/AGENTS.md`](packages/retrosheetpy/AGENTS.md) | Standalone Python-only Retrosheet client and parser package (no `mlb_baseball` dependency). In progress: production ingest uses the Chadwick C tools (ADR-299). |
| [`scripts/AGENTS.md`](scripts/AGENTS.md) | Operational/maintenance scripts and destructive-operation safety. |
| [`tests/AGENTS.md`](tests/AGENTS.md) | Pytest structure, real PostgreSQL integration, run-specific DB isolation. |
| [`transforms/AGENTS.md`](transforms/AGENTS.md) | SQLMesh models, audits, incrementality, PIT transformation contracts. |

Directories not indexed here inherit this root contract until they develop a
stable, distinct ownership/workflow boundary that justifies a local DOX file.
