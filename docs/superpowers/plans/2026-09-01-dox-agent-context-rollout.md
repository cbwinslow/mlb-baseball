# DOX multi-agent context rollout — 2026-09-01

Status: proposed implementation plan for owner review.

Design reference: `docs/AGENT_CONTEXT_ARCHITECTURE.md`.

This plan pilots Agent Zero's DOX concept in this repository while preserving
cross-tool compatibility with Codex, Claude Code, Gemini CLI / Gemini-based
agents, Agent Zero, and other `AGENTS.md`-aware tools.

The objective is not "more documentation." The objective is **less irrelevant
context, clearer local ownership, and fewer contradictory instructions**.

## 1. Desired end state

One canonical instruction hierarchy:

```text
AGENTS.md
├── mlb_baseball/AGENTS.md
│   ├── connectors/AGENTS.md
│   ├── sql/AGENTS.md
│   └── model/AGENTS.md        # while this legacy/frozen boundary exists
├── transforms/AGENTS.md
├── migrations/AGENTS.md
├── tests/AGENTS.md
├── docs/AGENTS.md
├── plans/AGENTS.md
└── scripts/AGENTS.md
```

Tool-specific adapters stay thin:

```text
CLAUDE.md     -> imports root AGENTS.md + Claude-only additions
GEMINI.md     -> imports root AGENTS.md + Gemini-only additions
CODEX.md      -> normally absent; Codex reads AGENTS.md natively
```

At child boundaries, add `CLAUDE.md` / `GEMINI.md` import bridges only where
needed to make vanilla/default tool behavior reliably load the local canonical
`AGENTS.md`.

This tree is illustrative. The pilot must prove each proposed child is a real
durable boundary before creating it.

## 2. Phase 0 — current-state audit and contradiction register

Before moving a single rule, inventory every instruction-bearing artifact that
can affect agent work:

- root `AGENTS.md`;
- root `CLAUDE.md`;
- `.claude/` rules/settings/skills/subagents if present;
- any current/future `GEMINI.md`;
- `.github/copilot-instructions.md` if present;
- Cursor/Windsurf/OpenCode rules if present;
- `docs/NORTH_STAR.md`;
- `docs/ARCHITECTURE.md`;
- `docs/PRODUCT_DIRECTION.md`;
- `docs/ROADMAP.md`;
- `docs/SQL_OWNERSHIP.md`;
- `docs/SOURCE_RIGHTS.md`;
- `plans/README.md` and active plans;
- important runbooks that root agent docs currently paraphrase.

Build a temporary reconciliation table with columns:

| Rule/topic | Current owners | Conflict? | Canonical owner | Local child | Action |
|---|---|---|---|---|---|
| test database isolation | AGENTS, CLAUDE, README | yes | tests/AGENTS | tests | reconcile |
| production DB safety | AGENTS, CLAUDE | overlap | root AGENTS | none | dedupe |
| connector idempotency | AGENTS, CLAUDE | overlap | connectors/AGENTS | connectors | move |
| SQL ownership | AGENTS, SQL_OWNERSHIP | overlap | docs + local AGENTS | sql/transforms | link |
| model promotion | AGENTS, CLAUDE, ADRs | overlap | model/AGENTS + ADR | model | move/link |

The table may live only in the implementation PR description or a temporary plan
section; do not create a permanent registry unless it proves useful.

### Known contradiction to resolve first

Current root doctrine describes/requires a fixed `mlb_test` test database in
places, while current README/testing behavior describes per-run isolated
uniquely-named pytest databases using the base test connection and says `mlb_test`
is not modified by tests.

The implementation must verify actual `tests/conftest.py` behavior and make the
code the observation source before rewriting documentation. Do not choose a side
from memory.

### Phase 0 gate

- every root instruction is classified as global, local, tool-specific, stale,
  duplicate, or detailed-reference-only;
- actual test database behavior is verified from code/tests;
- no rule is moved until its canonical owner is named.

## 3. Phase 1 — shrink and clarify root `AGENTS.md`

### Goal

Turn the root file from a broad encyclopedia into a durable project rail + map.

### Keep at root

Only invariants that apply to most/all changes:

- current product focus and mission;
- PostgreSQL is authoritative; production DB safety;
- source rights and provenance honesty;
- point-in-time/leakage honesty;
- preserve/reuse existing assets before adding new architecture;
- established-library check for cross-cutting infrastructure;
- measure before optimization/rewrite;
- Git/PR/worktree safety;
- general verification/definition-of-done expectations;
- delegation safety that applies repository-wide;
- Child DOX Index;
- links to current product/architecture/roadmap docs.

### Move down

Examples:

- connector retry/idempotency/raw artifact rules -> connectors child;
- SQL placement rules -> sql/transforms children plus `docs/SQL_OWNERSHIP.md`;
- test database/fixture rules -> tests child;
- model ladder/promotion detail -> model child + research docs/ADRs;
- docs history/map rules -> docs child;
- migration-specific destructive DDL rules -> migrations child;
- shell/script DB-target/dry-run rules -> scripts child.

### Root style

Use DOX-compatible sections where they help, but do not force every root concept
into the exact child template. Suggested root shape:

```text
# MLB project contract
## Mission and current focus
## Global invariants
## Work and verification doctrine
## Git/delegation safety
## Project map / sources of truth
## Child DOX Index
```

Target roughly 100–150 lines if practical. This is a quality target, not a hard
CI limit.

### Gate

A reviewer can read root `AGENTS.md` in a few minutes and know:

- what the project currently is;
- what must never be violated;
- where to look for the subsystem being edited;
- how to verify work at a high level.

## 4. Phase 2 — create first child contracts

Start with the boundaries that have the strongest evidence of distinct rules.
Do not create all possible children in one mechanical sweep unless the audit
shows they are all genuinely useful.

### 4.1 `tests/AGENTS.md` — first pilot child

This should be the first child because it resolves a known root contradiction and
has clear local rules.

Suggested content:

#### Purpose

Protect correctness with pure unit tests and real-PostgreSQL integration tests
without touching production data.

#### Ownership

- `tests/unit/**`
- `tests/integration/**`
- test fixtures and database-isolation behavior
- network fixture policy

#### Local Contracts

- verified current database clone/isolation behavior;
- production DB must never be a test target;
- real PostgreSQL for DB behavior; do not mock transactions/locks/COPY contracts;
- network mocked/captured for deterministic tests;
- failed transactions rolled back before teardown queries;
- fixtures own and clean their state;
- no order dependence;
- current accepted approach to per-worker DB isolation once xdist is adopted.

#### Verification

Exact current commands from CI/pyproject, not remembered commands.

#### Child DOX Index

Initially none unless integration/unit genuinely diverge enough later.

### 4.2 `mlb_baseball/connectors/AGENTS.md`

Own connector/source-specific contracts:

- bootstrap/update/backfill capabilities;
- health checks;
- run tracking;
- idempotency;
- bounded retry/rate limiting;
- source artifacts/checksums/replay;
- rights/profile checks;
- schema drift;
- raw/source-faithful naming;
- no third-party SDK object model leaking into core research schema.

Do not immediately add one child per connector. `mlb_api` may eventually justify
its own child after decomposition because it is a subsystem; small connectors do
not.

### 4.3 `docs/AGENTS.md`

Own:

- living vs dated snapshot semantics;
- `docs/MAP.md` maintenance;
- source/citation standards;
- generated docs vs curated docs;
- no duplicating current state in many places;
- when an ADR/spec/runbook is the correct artifact;
- archive/delete stale material instead of appending explanations forever.

### 4.4 `migrations/AGENTS.md`

Own:

- forward-only migration policy;
- naming/ordering;
- explicit target DB warning;
- transactional behavior;
- extension policy;
- schema/table-contract updates;
- integration verification.

### 4.5 `transforms/AGENTS.md`

Own SQLMesh rules:

- set-based derived transformations;
- incremental model contracts;
- audits/tests/tie-outs;
- no source identity reconciliation or model training;
- no second transform runtime.

### 4.6 `scripts/AGENTS.md`

Own operational shell/Python script safety:

- shebang and strict shell mode where applicable;
- prerequisite checks;
- explicit production/test DB target;
- dry-run for destructive one-time operations where feasible;
- logs and clear non-zero failure;
- no hidden production writes;
- idempotency/resume where appropriate.

### Phase 2 gate

For each child:

- content was moved/reconciled, not duplicated wholesale;
- root index describes its scope;
- no child weakens global safety/research invariants;
- local file is concise enough to be useful;
- exact verification commands are current.

## 5. Phase 3 — Python package/model child boundaries

Only after the first children prove useful.

### `mlb_baseball/AGENTS.md`

Own package-wide architecture:

- dependency direction;
- public facade/backward compatibility;
- typed contracts (`Protocol`, `StrEnum`, frozen/slotted dataclasses where they
  solve a real current need);
- pure stats/simulation import boundary;
- no speculative plugin inheritance tree;
- module sizing/decomposition philosophy;
- child index.

### `mlb_baseball/model/AGENTS.md`

While the current package exists, own:

- point-in-time contracts;
- promotion/evaluation doctrine;
- chronological folds;
- model artifact/provenance rules;
- deterministic model inference;
- frozen Engine-package rule;
- distinction between research stat and predictive feature.

When the package is later reorganized, move this contract with the durable
conceptual boundary rather than preserving a stale path for compatibility alone.

### `mlb_baseball/sql/AGENTS.md`

Own package SQL resources:

- SQL ownership rules;
- named resources;
- psycopg placeholder/comment gotchas;
- mutating vs read-only conventions;
- SQLFluff expectations;
- parity/contract tests.

## 6. Phase 4 — Claude bridge design

Anthropic's current official guidance says Claude Code reads `CLAUDE.md`, not
`AGENTS.md`, and recommends importing `AGENTS.md` to avoid duplication.

### Root change

Refactor root `CLAUDE.md` toward:

```markdown
@AGENTS.md

# Claude Code adapter

<only Claude-specific repository behavior>
```

Do not delete valuable existing rules until they have a verified canonical home.
The migration PR should show a rule-by-rule mapping for substantive deletions.

### Child bridges

For each child DOX boundary used by Claude, add a small file:

```text
<boundary>/CLAUDE.md
```

with:

```markdown
@AGENTS.md
```

plus local Claude-only behavior only if necessary.

Verify actual Claude Code loading with `/context`, `/memory`, or the current
supported instruction-inspection mechanism before declaring the bridge complete.

### `.claude/rules/`

Use for Claude-specific path-scoped behavior that should not be a canonical
project rule. Examples might include a Claude-only planning workflow or tool-use
preference. Do not mirror all child AGENTS content into `.claude/rules/`.

## 7. Phase 5 — Gemini bridge design

Gemini CLI currently supports hierarchical/JIT `GEMINI.md` files and `@` imports.
It also supports configuring `context.fileName` with multiple filenames such as
`AGENTS.md`.

### Portable repository default

Create root:

```text
GEMINI.md
```

with:

```markdown
@AGENTS.md
```

plus only Gemini-specific shared behavior if any.

At child DOX boundaries, add small `GEMINI.md` import bridges when the default
Gemini loader needs them for local context.

### Configured-user optimization

Document that users may configure Gemini to load `AGENTS.md` directly, but do not
make project correctness depend on a personal global setting.

### Antigravity/Agy delegation

Even with hierarchical files, bounded delegated prompts should remain
self-contained:

- exact task/scope;
- applicable plan;
- edits allowed/not allowed;
- DB safety;
- verification expected;
- changed-file/test/limitation handoff;
- no merge/next-package authority.

Different orchestration products can decide differently how much parent context a
subagent receives.

## 8. Phase 6 — Codex handling

No `CODEX.md` implementation is needed by default.

Codex directly supports the canonical `AGENTS.md` hierarchy and deeper-scoped
instructions. The implementation should verify the actual loaded chain in a
representative Codex session.

If a later use case needs Codex-only repository guidance:

1. first ask whether it belongs in user Codex configuration;
2. otherwise use a minimal documented adapter/fallback mechanism;
3. never create a second full project doctrine in `CODEX.md`.

## 9. Phase 7 — lightweight DOX validation

Do not add validation until the manual hierarchy is stable enough that we know
what should be enforced.

Candidate `scripts/check_agent_docs.py` responsibilities:

1. find all canonical `AGENTS.md` files;
2. parse each `Child DOX Index` using a deliberately simple format;
3. verify indexed child files exist;
4. verify every non-root canonical child has exactly one nearest parent index;
5. verify known bridge files are small and reference/import the adjacent
   `AGENTS.md`;
6. warn on oversized root/child docs;
7. detect a small set of high-risk contradictory literals only if false positives
   are low (e.g. old fixed test-database claims after migration);
8. exit non-zero only for structural breakage, not subjective prose quality.

Keep the script dependency-free or standard-library-only unless a parser library
provides a clear benefit.

Add to CI/pre-commit only after local testing proves it does not create noise.

## 10. Phase 8 — documentation/system-of-record cleanup enabled by DOX

Once local contracts exist, reduce duplicated current-state prose elsewhere.

Examples:

- `AGENTS.md` links to `docs/ARCHITECTURE.md` rather than restating full schema
  rationale;
- `tests/AGENTS.md` owns test procedure while README gives user-facing setup;
- `docs/AGENTS.md` points dated specs to current living docs;
- generated registries produce source/stat/CLI reference where possible.

The hierarchy should make `docs/MAP.md` simpler over time, not add another map that
must be reconciled manually.

## 11. Phase 9 — evaluate adjacent `*.dox.md`

Do this only after the AGENTS hierarchy works.

Pilot at most one or two modules that genuinely benefit from an adjacent contract,
for example a large gravity-well module during decomposition. Compare:

- agent edit accuracy;
- time to understand the module;
- duplication with docstrings/tests/AGENTS;
- maintenance burden after subsequent code changes.

Reject repo-wide adjacent DOX files if the same value comes from subtree contracts,
typed APIs, tests, and docstrings.

## 12. Phase 10 — cross-project template

If the MLB pilot demonstrates value, create a reusable template outside this
repository containing only generic material.

Suggested generic structure:

```text
AGENTS.md
CLAUDE.md
GEMINI.md

docs/AGENTS.md
src/AGENTS.md
tests/AGENTS.md
```

Generic root contract should include placeholders for:

- mission/current scope;
- global invariants/safety;
- architecture map;
- verification commands;
- Git workflow;
- Child DOX Index.

Generic child template:

```markdown
# <subsystem> contract

## Purpose

## Ownership

## Local Contracts

## Work Guidance

## Verification

## Child DOX Index
```

Do not carry MLB-specific PostgreSQL/model/rights rules into unrelated projects.

### Distribution options

Prefer, in order:

1. starter/template repository;
2. small local scaffolding script;
3. optional repository bootstrap skill for Claude/Codex/Gemini/A0.

Avoid a live remote include, mandatory runtime, or Git submodule for project
doctrine. A checked-out repository should contain the exact instructions that
match its code commit.

## 13. Measuring whether DOX actually helps

The pilot should collect qualitative and lightweight quantitative evidence.

Possible measures over several PRs:

- root always-loaded instruction lines/tokens before vs after;
- number of review findings caused by an agent missing a local rule;
- number of contradictory/stale instruction fixes;
- number of files an agent touches outside task scope;
- time/retries needed for an agent to find verification commands;
- agent self-reported applicable instruction chain in PR handoff;
- human reviewer assessment of whether local contracts helped or merely added
  ceremony.

Do not claim performance gains from DOX without this evidence.

## 14. Rollback criteria

Simplify or roll back parts of the hierarchy if:

- child docs regularly repeat parent text;
- contributors cannot tell which file owns a rule;
- tool-specific bridge files frequently drift;
- agents load more context than before without better accuracy;
- every code edit triggers noisy documentation churn;
- validation scripts become more complex than the documentation problem.

The canonical `AGENTS.md` concept can still be retained even if a deeper tree is
reduced.

## 15. PR slicing

Implement as reviewable PRs, not one giant doctrine rewrite.

### PR A — audit + testing pilot

- verify actual test DB behavior;
- add `tests/AGENTS.md`;
- reconcile root test doctrine;
- add root Child DOX Index;
- no other subtree changes.

### PR B — connectors + docs children

- `connectors/AGENTS.md`;
- `docs/AGENTS.md`;
- move/dedupe applicable root rules;
- verify existing workflows/docs.

### PR C — SQL/transforms/migrations/scripts

- create only children justified by audit;
- move specialized operational rules;
- keep global destructive-DB invariant at root.

### PR D — Claude/Gemini adapters

- shrink root `CLAUDE.md` into `@AGENTS.md` adapter after all migrated rules have
  canonical homes;
- add minimal `GEMINI.md`;
- add child bridges where verified necessary;
- test instruction loading in the actual tools available.

### PR E — validator

- only if manual pilot is successful;
- add structural checker + CI/pre-commit integration;
- no NLP or complicated policy engine.

### PR F — cross-project template

- separate repository/template work after MLB acceptance;
- document lessons and boundaries; do not copy MLB doctrine.

## 16. Acceptance criteria for the MLB pilot

The pilot is complete when:

1. there is one obvious canonical rule source for every sampled topic;
2. root `AGENTS.md` is materially shorter and more navigational;
3. Codex receives canonical local rules natively;
4. Claude receives root and sampled local rules through verified CLAUDE bridges;
5. Gemini receives root and sampled local rules through verified GEMINI bridges or
   documented supported configuration;
6. Agent Zero can use the same canonical tree without project-specific runtime;
7. the test-database contradiction is resolved from verified code behavior;
8. no full duplicated `CODEX.md`/`GEMINI.md`/`CLAUDE.md` doctrine exists;
9. agents can state the instruction chain applicable to a changed file;
10. human review finds the system easier to navigate than the prior root-only
    documents.

## 17. Recommendation

Proceed with PR A after the current research-grain PR stack is stable enough not
to create unrelated merge churn.

The first implementation should be intentionally small: root index +
`tests/AGENTS.md` + reconciliation of the known test instruction conflict. If that
small slice is not clearly useful, stop before building a larger hierarchy.

If it is useful, continue through connector/docs boundaries, then add Claude and
Gemini bridges, then consider automation.