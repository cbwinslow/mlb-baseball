# DOX repository-knowledge rollout — 2026-09-01

Status: proposed implementation plan for owner review.

Design reference: `docs/AGENT_CONTEXT_ARCHITECTURE.md`.

This plan implements Agent Zero's DOX model as a **recursive, source-adjacent
repository knowledge protocol**. It replaces the earlier narrower plan that
focused mostly on nested `AGENTS.md` files.

The intended result is not simply more instruction files. It is a navigable
knowledge tree that lets an agent discover the exact contracts for the code it is
about to change:

```text
root AGENTS.md
   ↓
subsystem/AGENTS.md
   ↓
source_file.py.dox.md   # when local profile requires file-level DOX
   ↓
source + tests + linked authoritative docs
```

The protocol must remain useful to Codex, Claude Code, Gemini/Agy, Agent Zero,
and humans without depending on a proprietary runtime.

# 1. Non-negotiable DOX principles

1. `AGENTS.md` is a recursive contract/index, not merely a prompt file.
2. The closest applicable directory DOX owns local subsystem behavior.
3. A local `AGENTS.md` may declare the directory a **file-documented DOX
   profile**.
4. In a file-documented profile, direct source files have same-directory
   `<full-filename>.dox.md` contracts.
5. Source owns implementation; DOX owns durable knowledge about that
   implementation.
6. Before editing, agents traverse the applicable DOX path and load only relevant
   local contracts.
7. After meaningful changes, agents update affected sidecars/contracts/indexes in
   the same change.
8. DOX summarizes and routes to authoritative structured sources; it must not
   compete with the Stat Registry, table contracts, ADRs, tests, or code.
9. No child may weaken parent-level safety/research contracts.
10. Stale DOX is removed or corrected immediately rather than preserved as
    historical narrative.

# 2. Target architecture

A likely mature topology is:

```text
AGENTS.md
├── mlb_baseball/AGENTS.md
│   ├── connectors/AGENTS.md          # file-documented profile
│   │   ├── mlb_api.py
│   │   ├── mlb_api.py.dox.md
│   │   ├── retrosheet.py
│   │   ├── retrosheet.py.dox.md
│   │   └── ...
│   ├── stats/AGENTS.md               # future file-documented profile
│   ├── research/AGENTS.md
│   ├── model/AGENTS.md
│   └── sql/AGENTS.md
├── transforms/AGENTS.md
├── migrations/AGENTS.md
├── tests/AGENTS.md
├── docs/AGENTS.md
├── plans/AGENTS.md
└── scripts/AGENTS.md
```

Tool adapters:

```text
CLAUDE.md      thin bridge + Claude-only behavior
GEMINI.md      thin bridge + Gemini-only behavior
CODEX.md       normally absent; Codex consumes AGENTS.md directly
```

Selected root/gravity-well source files may also have sidecars while the package
is being reorganized:

```text
mlb_baseball/cli.py.dox.md
mlb_baseball/conform.py.dox.md
```

The exact tree is created from current repository evidence, not copied blindly
from Agent Zero.

# 3. Phase 0 — truth and instruction audit

Before creating the DOX tree, identify all durable instructions and resolve known
contradictions.

Inventory:

- root `AGENTS.md`;
- root `CLAUDE.md`;
- `.claude/` project rules/settings/skills;
- any `GEMINI.md` or other checked-in agent rules;
- `docs/NORTH_STAR.md`;
- `docs/PRODUCT_DIRECTION.md`;
- `docs/ARCHITECTURE.md`;
- `docs/SQL_OWNERSHIP.md`;
- `docs/SOURCE_RIGHTS.md`;
- `docs/TABLE_CONTRACTS.md`;
- `docs/ROADMAP.md`;
- `plans/README.md` and active plans;
- verification commands encoded in CI/pre-commit/pyproject;
- source-level comments that contain unique durable contracts.

Build a temporary reconciliation matrix:

| Topic | Current locations | Observed truth | Canonical DOX owner | Detailed source |
| --- | --- | --- | --- | --- |
| test DB isolation | AGENTS, CLAUDE, README | verify from fixtures | `tests/AGENTS.md` | tests/conftest.py |
| production DB safety | AGENTS, CLAUDE | verify current | root AGENTS | code/runbook |
| connector idempotency | AGENTS, CLAUDE | current contract | connectors AGENTS | tests/docs |
| source rights | several | current profiles | root + connector sidecars | source_profiles |
| stat formulas | model/docs/tests | per-stat | stats DOX summary | Stat Registry |

## First known contradiction

The current root agent doctrine and current README describe test database behavior
differently. Determine the actual behavior from `tests/conftest.py` and relevant
tests before changing either statement.

## Phase 0 gate

- every substantive root rule has a named canonical owner;
- contradictions have an observed source of truth;
- no stale rule is copied into a new DOX file merely because it existed before.

# 4. Phase 1 — establish root DOX rail

Refactor root `AGENTS.md` into a concise global contract and top-level Child DOX
Index.

Root retains only project-wide invariants:

- research database is the current product focus;
- PostgreSQL/system-of-record safety;
- source-rights/provenance honesty;
- point-in-time/leakage honesty;
- reuse existing assets before inventing frameworks;
- measure before rewrites/optimizations;
- Git/PR/worktree safety;
- general verification expectations;
- DOX traversal/update protocol;
- Child DOX Index;
- links to current architecture/product/roadmap docs.

Move subsystem-specific instructions down instead of duplicating them.

## Root DOX workflow text must explicitly say

Before editing:

1. identify every target path;
2. read root DOX;
3. traverse all indexed child DOX that contain the target;
4. obey the nearest local profile;
5. if the local profile requires file sidecars, read each target's matching
   `.dox.md` before editing.

After editing:

1. update affected file sidecars when durable contracts changed;
2. update directory contracts when responsibilities/workflows changed;
3. update parent indexes when structure changed;
4. delete stale sidecars/index rows after moves/deletes;
5. run local verification.

# 5. Phase 2 — first child DOX: tests

Create `tests/AGENTS.md` first because testing has a known instruction conflict and
strong local safety semantics.

It owns:

- unit vs integration boundaries;
- actual verified PostgreSQL test-database isolation behavior;
- production DB prohibition;
- fixture ownership and cleanup;
- rollback after failed transactions;
- network fixture policy;
- test-order independence;
- eventual xdist worker isolation;
- exact current verification commands.

Do **not** create sidecars for every test file. Tests are executable evidence for
other contracts, not a flat component API needing its own prose twin.

## Phase 2 gate

A new agent editing `tests/integration/...` can determine database safety and
verification rules from root -> `tests/AGENTS.md` without reading model or
connector doctrine.

# 6. Phase 3 — connectors as first file-documented profile

This is the most important corrected part of the rollout.

Create `mlb_baseball/AGENTS.md` if needed for package-wide dependency/public API
contracts, then create:

```text
mlb_baseball/connectors/AGENTS.md
```

Declare it a **file-documented DOX profile**, analogous to Agent Zero's
`api/`, `helpers/`, and `tools/` directories.

The local contract should require a matching `*.dox.md` sidecar for each direct
connector implementation that participates in the supported connector registry.

Example:

```text
retrosheet.py
retrosheet.py.dox.md

kalshi.py
kalshi.py.dox.md
```

## Connector sidecar template

```markdown
# <connector>.py DOX

## Purpose

## Ownership
- source family
- raw relations/artifacts owned
- public connector entry points

## Source Contracts
- upstream endpoint/files
- rights/profile
- historical/current coverage
- source-native identity/scope

## Runtime Contracts
- bootstrap/update/backfill
- idempotency
- retry/rate limit
- artifact/replay behavior
- schema drift/null handling
- side effects

## Key Dependencies
- internal helpers
- external library/client
- downstream conform consumers

## Work Guidance

## Verification
- integration tests
- health checks
- relevant replay/fixture checks

## Child DOX Index
No child DOX files.
```

## How to bootstrap sidecars safely

For each connector:

1. read the implementation;
2. read registry entry;
3. read its integration tests;
4. read source-rights/data-source docs;
5. read relevant migration/raw table contract;
6. capture only durable, verified facts;
7. link to detailed docs instead of restating them;
8. mark unknowns as unknown rather than inferring behavior.

## Phase 3 gate

- direct connector coverage is complete for the declared profile;
- every sidecar identifies verification evidence;
- sidecars do not reproduce raw schemas or giant source documentation;
- registry/source-profile changes update relevant sidecars in the same PR.

# 7. Phase 4 — high-value gravity-well file DOX

Add sidecars for large modules where orientation cost is high even if their
parent directory is not yet a full file-documented profile.

Priority candidates:

- `mlb_baseball/cli.py`;
- `mlb_baseball/conform.py`;
- `mlb_baseball/connectors/mlb_api.py` (already covered by connectors profile);
- `mlb_baseball/load.py`;
- `mlb_baseball/report.py`;
- `mlb_baseball/public.py`.

These sidecars should document responsibility maps rather than paraphrase every
function.

For `conform.py`, for example:

- identity responsibilities;
- game resolution/backfills;
- plays/pitches;
- market normalization;
- order dependencies;
- honest-null policy;
- relevant table contracts/tests.

For `cli.py`:

- parser/dispatch ownership;
- stable public commands;
- command groups;
- frozen Engine surface;
- behavior-preserving decomposition constraints;
- dispatch tests.

When these files are split, move/split the DOX contracts with the implementation.

# 8. Phase 5 — docs/plans/migrations/transforms directory DOX

Create directory-level DOX where local workflows differ materially.

## `docs/AGENTS.md`

Own:

- living vs dated snapshot distinction;
- current-doc map/index responsibilities;
- citation/source policy;
- generated vs curated docs;
- archival rules;
- no current-state duplication across many docs.

Normally no sidecar for every Markdown document. The documents themselves are
human-facing content.

## `plans/AGENTS.md`

Own:

- active vs historical plan semantics;
- progress/evidence recording;
- plan sequencing and closeout;
- no stale plan presented as current product direction.

## `migrations/AGENTS.md`

Own:

- forward-only numbering;
- production target safety;
- DDL/extension rules;
- schema/table contract updates;
- integration verification.

Do not create one `.dox.md` sidecar per migration by default. The migration SQL
and its comments are already the local implementation artifact.

## `transforms/AGENTS.md`

Own:

- SQLMesh domain boundary;
- incrementality;
- audits/tests/tie-outs;
- grain/time semantics;
- promotion policy;
- no procedural identity or ML training.

File-level sidecars for particularly complex long-lived SQLMesh models can be
added later if they provide real contract value.

# 9. Phase 6 — model package DOX without doubling the legacy engine pile

The `model/` directory is unusually large and contains many frozen/legacy Engine
modules.

Do not immediately generate 100+ generic sidecars.

First create `model/AGENTS.md` covering:

- point-in-time rules;
- chronological evaluation;
- artifact/provenance behavior;
- frozen Engine-package policy;
- research-stat vs predictive-feature distinction;
- child domain roadmap.

Then classify modules into durable domains as the consolidation plan proceeds:

```text
stats/
simulation/
models/
evaluation/
legacy-or-prototypes/
```

Declare file-documented profiles only after those boundaries stabilize.

For currently load-bearing pure modules (Markov core, evaluation, GBM, etc.),
individual sidecars may be worthwhile before the full reorganization if they
capture meaningful contracts.

# 10. Phase 7 — future stats and ResearchDB DOX

When the neutral `stats/` package is created, strongly consider making it a
file-documented profile.

A stat module sidecar should link to the machine-readable Stat Registry and
capture module-level ownership rather than duplicate every formula field.

Useful DOX concepts:

- domain/grain;
- authoritative registry IDs;
- pure-function/import expectations;
- allowed dependencies;
- PIT vs finalized-stat role;
- cross-language parity obligations;
- hand-fixture/tie-out test paths.

For `research/`, file-level DOX should capture stable public query contracts:

- filters;
- return types/backends;
- rights behavior;
- relation ownership;
- compatibility expectations;
- query tests.

# 11. Phase 8 — Claude/Codex/Gemini bridge behavior

## Codex

Codex already understands hierarchical `AGENTS.md`. Its applicable local DOX then
instructs it to read sidecars before source edits.

No full `CODEX.md` copy.

## Claude Code

Refactor root `CLAUDE.md` toward a thin import/adapter of canonical DOX plus only
Claude-specific behavior.

Use nested bridges or supported path-scoped rules so Claude sees local DOX
routing when working in a child subtree.

Once the child contract is visible, Claude can explicitly read source sidecars;
sidecars do not need native implicit loading.

## Gemini CLI / Agy

Use `GEMINI.md` imports or configure Gemini context filenames to include
`AGENTS.md`.

Delegated Agy prompts remain self-contained about task scope, DB safety, allowed
writes, and expected handoff because orchestration products may not propagate the
same repository context automatically.

## Agent Zero

Use the protocol directly.

# 12. Phase 9 — structural DOX validator

After the conventions stabilize, create a small structural validator.

Suggested responsibilities:

1. enumerate all `AGENTS.md` files;
2. validate parent Child DOX Index links;
3. ensure each non-root child has a nearest indexed parent;
4. identify directories explicitly declared file-documented;
5. ensure each required direct source file has a matching sidecar;
6. detect orphan sidecars;
7. validate required sidecar section headings;
8. validate referenced local test/doc paths where practical;
9. keep tool adapter files within a small size budget;
10. fail only on structural contract violations, not subjective prose quality.

Use standard library Python initially.

Potential command:

```bash
uv run python scripts/check_dox.py
```

After it proves quiet and useful, add it to pre-commit and CI.

# 13. Phase 10 — DOX freshness discipline

Add DOX to definition-of-done for behavioral changes.

A PR that changes a documented component should answer:

- Did its public/local contract change?
- Did inputs/outputs/side effects change?
- Did ownership move?
- Did verification change?
- Did a dependency/source/rights assumption change?
- Does its sidecar need updating?
- Does a parent index need updating?

No change is required when a refactor preserves every durable contract; the agent
should still perform the check.

For file-documented profiles, CI covers structural freshness (presence/orphans).
Semantic freshness remains a code-review concern.

# 14. Phase 11 — measure whether DOX helps

Do not evaluate success by file count.

Track qualitative/quantitative evidence across several real tasks:

- time/tokens spent discovering a module's responsibility;
- number of irrelevant files agents open before edits;
- rate of duplicated helpers/abstractions;
- rate of forgotten tests/docs/health checks;
- reviewer findings caused by missing local context;
- contradictions found between old docs and implementation;
- frequency of sidecar updates after behavioral changes;
- whether sidecars remain concise after several development cycles.

Test with at least Codex, Claude Code, and Gemini/Agy-style work if possible.

Success means agents make more precise changes with less rediscovery and fewer
missed local contracts.

# 15. Phase 12 — cross-project standardization

If the MLB rollout remains useful after normal churn, create a reusable DOX
bootstrap/template for other repositories.

Generic initializer behavior:

1. inventory top-level durable subsystem boundaries;
2. create root DOX contract/index;
3. create child contracts for genuine boundaries;
4. identify flat, contract-heavy directories suited to file-documented profiles;
5. generate initial sidecars from source + tests + existing docs;
6. flag uncertain facts for review;
7. run structural validation;
8. create thin vendor adapters only where needed.

Do not copy MLB-specific rules into unrelated projects.

# 16. Recommended PR sequence for this repository

Keep implementation reviewable.

## PR A — DOX foundation

- verify/reconcile root instruction contradictions;
- establish root DOX workflow/index;
- add `tests/AGENTS.md`;
- no mass sidecars yet.

## PR B — connector DOX profile

- add package/connectors `AGENTS.md` hierarchy;
- declare connectors file-documented;
- add sidecars for direct registered connector modules;
- add initial structural coverage check for that directory.

## PR C — gravity-well sidecars

- `cli.py.dox.md`;
- `conform.py.dox.md`;
- `load.py.dox.md` / `report.py.dox.md` where justified;
- use them to support the planned decomposition work.

## PR D — docs/migrations/transforms/plans DOX

- add local directory contracts;
- move/dedupe existing root rules;
- update root index.

## PR E — tool bridges + validator

- thin Claude/Gemini adapters;
- mature structural validator;
- pre-commit/CI only after local proof.

## Later

- stats/research file profiles when those packages exist;
- model profile expansion after module classification;
- reusable cross-project DOX template.

# 17. Completion criteria

The rollout is successful when:

- a fresh agent can locate all applicable contracts for a target path without
  searching the entire docs tree;
- file-documented profiles have complete sidecar coverage;
- sidecars describe non-obvious durable contracts rather than generic summaries;
- moves/deletes cannot leave orphan sidecars/indexes unnoticed;
- root agent context is materially smaller and less contradictory;
- Claude/Codex/Gemini can all traverse the same canonical knowledge;
- DOX links cleanly to tests, registries, table contracts, rights docs, and ADRs;
- documentation stays current through several real PRs;
- the system reduces rediscovery instead of becoming another documentation burden.

## Bottom line

The implementation target is not a collection of nested prompts.

It is a **self-maintaining, recursively indexed knowledge layer colocated with the
repository structure and, where valuable, with the individual source files
itself**.

That is the DOX protocol this project should pilot.