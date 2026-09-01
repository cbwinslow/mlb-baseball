# DOX progressive-context rollout — 2026-09-01

Status: proposed implementation plan for owner review.

Design references:

- `docs/AGENT_CONTEXT_ARCHITECTURE.md`
- `docs/PROGRESSIVE_CONTEXT_ARCHITECTURE.md`

This plan implements DOX as **progressive disclosure of repository knowledge
through filesystem scope**, while preserving first-class agent-specific behavior
for Claude Code, Codex, Gemini/Agy, Agent Zero, and future harnesses.

The goal is not to make every agent read identical files. The goal is:

> every agent starts with a small amount of global context, follows the
> filesystem to discover the exact project knowledge relevant to the files it is
> changing, and also receives any native tool-specific instructions that make
> that harness work correctly.

## 1. Desired end state

Conceptually:

```text
shared project knowledge                    agent-specific behavior
----------------------------------------    ------------------------------
AGENTS.md                                   CLAUDE.md
  -> package/AGENTS.md                        -> nested CLAUDE.md as needed
    -> subsystem/AGENTS.md                    -> .claude/rules/
      -> source.ext.dox.md                    -> .claude/skills/

                                             GEMINI.md / Gemini config
                                             Codex config/instructions
                                             Agent Zero profile/project config
```

Deep references remain outside prompt/context contracts:

```text
source code
unit/integration tests
Stat Registry
Table Contracts
docs/SOURCE_RIGHTS.md
ADRs
runbooks
research citations
```

The local DOX layer summarizes and routes to these sources when necessary.

## 2. Core principles

### 2.1 Progressive disclosure

Context is loaded from broad to specific:

```text
root invariants
    -> domain/subsystem contract
        -> exact implementation sidecar
            -> exact tests/reference docs
                -> task-specific skill/runbook only when needed
```

Do not preload unrelated branches of project knowledge.

### 2.2 Two-scope classification

Before moving any current rule, classify it twice:

1. **filesystem scope** — repository, package, subsystem, file, or task;
2. **agent scope** — shared, Claude-specific, Codex-specific, Gemini-specific,
   Agent Zero-specific, or human/operator-only.

A rule can be local and Claude-specific. It does not need to become shared merely
because it is durable.

### 2.3 Shared facts are not agent behavior

Examples of shared facts/contracts:

- raw/core/gold/meta architecture;
- Retrosheet rights and coverage;
- connector idempotency;
- production DB must never be used by tests;
- wOBA formula source;
- point-in-time availability semantics.

Examples of agent-specific behavior:

- Claude should use a particular planning/review workflow;
- Claude should invoke a project skill for a class of changes;
- Gemini/Agy delegation handoffs must use a specific format;
- a Codex-specific environment or verification preference.

Keep these categories separate.

## 3. Phase 0 — instruction and context census

Inventory every current artifact that can influence agent work:

- root `AGENTS.md`;
- root `CLAUDE.md`;
- `.claude/CLAUDE.md`, `.claude/rules/`, skills, settings if present;
- `GEMINI.md` / Gemini settings if present;
- Codex-specific project/global configuration if present;
- Agent Zero project/profile instructions if present;
- editor/agent rules for Cursor, Windsurf, OpenCode, Copilot, etc.;
- `docs/NORTH_STAR.md`;
- `docs/ARCHITECTURE.md`;
- `docs/PRODUCT_DIRECTION.md`;
- `docs/ROADMAP.md`;
- `docs/SQL_OWNERSHIP.md`;
- `docs/SOURCE_RIGHTS.md`;
- `plans/README.md` and active plans;
- current runbooks whose rules are paraphrased in root instructions.

Build a temporary reconciliation table:

| Topic | Existing locations | Filesystem scope | Agent scope | Canonical destination | Action |
| --- | --- | --- | --- | --- | --- |
| production DB safety | AGENTS, CLAUDE | repo | shared | root AGENTS | dedupe |
| test DB isolation | AGENTS, CLAUDE, README | tests | shared | tests/AGENTS | verify/reconcile |
| connector idempotency | AGENTS, CLAUDE | connectors | shared | connectors/AGENTS | move |
| Claude planning workflow | CLAUDE | repo or path | Claude | CLAUDE / rules | preserve/refine |
| model promotion | AGENTS, CLAUDE, docs | model | mostly shared | model/AGENTS + ADR | move/link |
| Agy delegation handoff | AGENTS/plan | delegated work | Gemini/Agy | Gemini/Agy skill/rule | separate |

Do not move rules until the destination is explicit.

### Phase 0 verification

- actual pytest DB isolation is checked from `tests/conftest.py` and tests;
- stale export/product statements are identified;
- Claude-specific rules are marked before any CLAUDE cleanup;
- no rule is declared duplicate merely because another agent has a similar one.

## 4. Phase 1 — root shared context becomes the rail

Refactor root `AGENTS.md` toward a compact map/invariant set.

Keep only near-universal shared context:

- current product focus;
- PostgreSQL authority and production-data safety;
- source-rights/provenance honesty;
- point-in-time/leakage honesty;
- reuse existing assets before inventing frameworks;
- measure before rewrites/optimizations;
- global Git/PR/worktree safety;
- high-level definition of verified work;
- Child DOX Index;
- pointers to current product/architecture/roadmap sources of truth.

Move local detail downward.

Target: concise enough that reading it on every task is cheap. Do not use a hard
line-count gate if that would damage clarity.

## 5. Phase 2 — preserve and restructure Claude-specific context

This phase is intentionally separate from root `AGENTS.md` cleanup.

Claude Code has legitimate requirements that other agents do not necessarily
share. Do **not** reduce `CLAUDE.md` to a one-line import unless all current
Claude-specific behavior has been intentionally relocated.

### 5.1 Root `CLAUDE.md`

Allowed structure:

```markdown
@AGENTS.md

# Claude-specific repository behavior

- Claude planning/review rules
- Claude subagent/delegation rules
- Claude skill-selection rules
- Claude MCP/plugin/hook rules
- Claude-specific verification behavior
- recurring Claude failure-mode corrections
```

Shared project facts should be imported/routed, not duplicated. Claude-specific
rules stay first class.

### 5.2 Nested Claude context

Use nested `CLAUDE.md` when Claude needs persistent instructions for a durable
subtree and that is clearer than a rule file.

Examples:

```text
mlb_baseball/model/CLAUDE.md
migrations/CLAUDE.md
tests/CLAUDE.md
```

Only create them when there is real Claude-local behavior.

### 5.3 `.claude/rules/`

Prefer path-scoped rules when the behavior applies conditionally to matching
files.

Examples:

```text
.claude/rules/migrations.md
.claude/rules/tests.md
.claude/rules/models.md
```

These files should specify **Claude behavior**, not duplicate the shared local
contract.

### 5.4 Claude skills

Move occasional, multi-step procedures to skills rather than permanent context.
Candidates:

- formula-validation workflow;
- dependency/library replacement evaluation;
- historical backfill/recovery;
- release/public-safe dataset verification;
- model-promotion review;
- PR review-comment resolution workflow.

This is progressive disclosure at the procedure level.

### Phase 2 verification

Use Claude's current context/memory inspection features to verify what actually
loads at root and inside representative subdirectories.

## 6. Phase 3 — first local shared contract: `tests/AGENTS.md`

Testing is a good pilot because current documentation already appears to contain
conflicting descriptions of test database isolation.

`tests/AGENTS.md` owns:

- unit vs integration boundary;
- actual current per-run database isolation behavior;
- production DB prohibition;
- real PostgreSQL rule for DB semantics;
- network fixture/mock policy;
- teardown rollback/cleanup behavior;
- no order dependence;
- current xdist/per-worker rules if/when adopted;
- exact verification commands from CI/pyproject.

If Claude has additional testing-specific workflow requirements, keep them in
`tests/CLAUDE.md` or path-scoped `.claude/rules`, not in the shared test contract.

### Gate

Perform equivalent testing tasks with at least Codex and Claude and confirm both
reach the right shared local knowledge without loading unrelated model/source
instructions.

## 7. Phase 4 — package and connectors hierarchy

Create `mlb_baseball/AGENTS.md` only after its responsibilities are clearly
separated from root.

It should own shared package architecture:

- dependency direction;
- supported public facade/backward compatibility;
- pure-domain vs DB import boundary;
- typing/Protocol/dataclass conventions where currently justified;
- naming rules local to package code;
- child routing/index.

Then create `mlb_baseball/connectors/AGENTS.md`.

Connector shared contract:

- bootstrap/update/backfill capability;
- health checks;
- source profiles/rights;
- artifact preservation/replay;
- retries/rate limits/timeouts;
- idempotency;
- schema drift;
- raw/source-faithful naming;
- no third-party SDK object model leaking into canonical research schema;
- exact test/doctor expectations.

## 8. Phase 5 — first file-documented DOX profile: connectors

This is the strongest candidate for Agent Zero-style file-level DOX.

Declare in `connectors/AGENTS.md` which files require a matching
`<filename>.dox.md` sidecar.

Possible policy options:

### Option A — every direct stable connector

```text
retrosheet.py -> retrosheet.py.dox.md
kalshi.py     -> kalshi.py.dox.md
polymarket.py -> polymarket.py.dox.md
...
```

### Option B — only complex/high-risk connectors initially

Start with:

- `mlb_api.py`;
- `retrosheet.py` / Retrosheet event connector;
- `kalshi.py`;
- `polymarket.py`.

Choose based on maintenance value, not aesthetics.

### Sidecar template

```markdown
# <filename> DOX

## Purpose
## Ownership
## Public/Runtime Contracts
## Source and Rights Contracts
## IDs and Grains
## Artifacts and Side Effects
## Important Dependencies
## Downstream Consumers
## Known Source Quirks
## Work Guidance
## Verification
## References
## Child DOX Index
```

Generate/populate from verified source, tests, schemas, and docs. Do not invent
contracts merely to fill sections.

### Gate

Ask an unfamiliar agent to make a bounded connector change using the DOX path and
compare understanding/edit accuracy against a control task without the sidecar.

## 9. Phase 6 — transitional sidecars for gravity wells

Pilot source-adjacent context on files that repeatedly cost agents substantial
reconnaissance time:

- `mlb_baseball/conform.py.dox.md`;
- `mlb_baseball/cli.py.dox.md`;
- `mlb_baseball/load.py.dox.md`;
- `mlb_baseball/report.py.dox.md`.

These are transitional documentation assets. As code is decomposed, move the
contracts to the new owning modules/subtrees and delete stale sidecars.

Do not preserve a sidecar merely because it once existed.

## 10. Phase 7 — SQLMesh, migrations, docs, scripts

Create local shared contracts only where there are durable, distinct rules.

### `transforms/AGENTS.md`

- SQLMesh ownership;
- grain/time/incremental contracts;
- audits/tie-outs;
- no procedural identity resolution or ML training;
- no second transform runtime.

### `migrations/AGENTS.md`

- forward-only migration policy;
- explicit target DB safety;
- extension policy;
- transaction behavior;
- schema/table-contract updates;
- integration verification.

### `docs/AGENTS.md`

- living vs dated snapshot distinction;
- `docs/MAP.md` ownership;
- source/citation standards;
- generated vs curated docs;
- archive/delete stale docs rather than accumulating contradictions.

### `scripts/AGENTS.md`

- strict shell mode where appropriate;
- prerequisites;
- explicit DB target;
- dry-run/destructive safety;
- logs/non-zero failures;
- idempotency/resume requirements.

Agent-specific local files are optional at each boundary and must be justified by
real agent-specific behavior.

## 11. Phase 8 — model/stat/research context after architecture stabilizes

Do not encode today's legacy model layout as permanent DOX architecture.

As the research platform refactor establishes stable domains, create shared
context for:

```text
mlb_baseball/stats/
mlb_baseball/research/
mlb_baseball/model/ or successor forecasting package
```

The `stats/` area should route to the machine-readable Stat Registry rather than
copying formulas into prose.

Possible sidecar relationships:

```text
stats/batting.py.dox.md
    -> Stat Registry IDs
    -> formula citations
    -> coverage metadata
    -> hand fixtures
    -> external tie-outs
```

Prediction/model context owns point-in-time, chronological evaluation, artifact,
and calibration contracts separately from finalized research statistics.

## 12. Phase 9 — Gemini/Agy context

Preserve Gemini-native behavior rather than assuming it is identical to Codex or
Claude.

- use Gemini hierarchical/JIT context;
- allow `GEMINI.md` to contain genuine Gemini-specific rules;
- optionally configure Gemini to recognize `AGENTS.md` as shared context;
- keep Agy delegation prompts/skills explicit when orchestration may not inherit
  all filesystem context automatically;
- use neutral DOX sidecars for project truth.

Verify actual context with Gemini's current memory/context inspection commands.

## 13. Phase 10 — Codex context

Codex natively fits the scoped shared `AGENTS.md` tree.

- verify nested instructions load for representative tasks;
- keep Codex-specific preferences in Codex-supported configuration when needed;
- do not add a full duplicate `CODEX.md` merely for symmetry;
- if a future Codex-only repo rule is necessary, add it through a supported
  Codex-specific mechanism and document why it is not shared.

## 14. Phase 11 — structural DOX validation

Only automate after the manual pattern is stable.

Candidate standard-library validator:

1. enumerate `AGENTS.md` files;
2. verify Child DOX Index paths exist;
3. verify non-root children are indexed by nearest owner;
4. for declared file-documented profiles, verify required source files have
   matching sidecars;
5. detect orphan sidecars after rename/delete;
6. optionally check required sidecar section headings;
7. check that agent bridge/rule files do not accidentally duplicate known large
   canonical blocks;
8. warn on oversized always-on root context;
9. fail only on structural errors, not subjective prose quality.

Add CI/pre-commit only after false-positive rate is low.

## 15. Phase 12 — measure whether this actually works

Do not declare success because a tree exists.

Measure:

- tokens/lines of always-on context per harness;
- number of context files loaded for representative tasks;
- time/reconnaissance required before an agent can safely edit a subsystem;
- frequency of stale/contradictory instruction findings;
- reviewer findings caused by missing project context;
- sidecar maintenance burden;
- whether agents update local context when contracts change;
- cross-agent handoff quality;
- rate of unnecessary unrelated file changes.

Representative tasks:

1. Retrosheet parser change;
2. PostgreSQL fixture/test change;
3. SQLMesh research mart change;
4. sabermetric formula/stat change;
5. CLI handler refactor;
6. documentation-only current-state correction.

Compare at least Codex, Claude Code, and Gemini/Agy when practical.

## 16. Phase 13 — cross-project standard

If the MLB pilot works, create a reusable CBW context architecture template.

Do **not** ship one giant universal `AGENTS.md` copied to every project.

Ship instead:

- a small root shared-contract template;
- a child DOX template;
- a file-sidecar template;
- guidance for declaring file-documented profiles;
- Claude-specific hierarchy/rules/skills guidance;
- Gemini-specific hierarchy guidance;
- Codex shared-hierarchy guidance;
- a structural validator template;
- criteria for deciding when a folder/file deserves local context.

Each project chooses boundaries based on its own architecture.

## 17. PR slicing

Recommended implementation slices:

### DOX-1 — truth census + testing pilot

- audit current instructions;
- verify pytest DB behavior;
- reconcile test contradiction;
- add/clean root Child DOX Index;
- add `tests/AGENTS.md`;
- preserve Claude-specific test/root behavior correctly.

### DOX-2 — package/connectors

- add `mlb_baseball/AGENTS.md`;
- add `connectors/AGENTS.md`;
- establish first file-documented profile policy;
- add a small representative set of connector sidecars.

### DOX-3 — gravity-well pilot

- add `conform.py.dox.md` and/or `cli.py.dox.md`;
- measure whether they reduce reconnaissance/edit errors.

### DOX-4 — transforms/migrations/docs/scripts

- add only verified durable local contracts;
- add agent-specific path rules where genuinely needed.

### DOX-5 — validation

- add structural checker;
- CI/pre-commit only after proving low noise.

### DOX-6 — stable research domains

- stats/research/model-local context after architecture settles;
- integrate Stat Registry references.

## 18. Acceptance criteria

The rollout is successful when:

- root context is materially smaller and more relevant;
- local folders contain enough context to make safe changes without reading the
  whole project doctrine;
- high-value source files can expose rich durable context without forcing that
  context into unrelated sessions;
- Claude retains its real Claude-specific requirements;
- Codex, Claude, Gemini/Agy, and Agent Zero can all reach the same project truth;
- agent-specific workflows are not incorrectly universalized;
- skills/runbooks absorb procedures that should load only on demand;
- stale instructions have clearer owners and are easier to remove;
- DOX maintenance cost is lower than the reconnaissance/review cost it replaces.

The key principle is simple:

> Spread knowledge across the filesystem according to scope so agents can load it
> progressively. Share project truth where possible, specialize agent behavior
> where necessary, and never spend context tokens on information unrelated to the
> current work.
