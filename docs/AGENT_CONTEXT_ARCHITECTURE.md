# Agent context architecture

Status: proposed durable design for owner review, 2026-09-01.

This document evaluates Agent Zero's DOX approach and adapts it to this repository's
real multi-agent workflow: OpenAI Codex, Claude Code, Gemini CLI / Antigravity-style
Gemini agents, Agent Zero, and similar coding agents.

The goal is **one project doctrine with local, hierarchical context**, not one
large instruction file per vendor.

## Decision summary

Adopt the core DOX idea, with one important portability change:

> `AGENTS.md` is the canonical project contract. Child `AGENTS.md` files define
> local contracts at durable subsystem boundaries. Tool-specific files such as
> `CLAUDE.md` and `GEMINI.md` are thin adapters to that canonical tree and contain
> only genuinely tool-specific instructions.

Do **not** maintain independent full copies of the same rules in `AGENTS.md`,
`CLAUDE.md`, `CODEX.md`, and `GEMINI.md`. That creates immediate drift and burns
context tokens on duplicated instructions.

Do **not** copy Agent Zero's entire adjacent `*.dox.md` file pattern into this
repository by default. Evaluate that separately for modules where an adjacent
contract adds value. The highest-value idea is the hierarchical `AGENTS.md` tree,
not the filename suffix.

Implementation is staged in:

- `docs/superpowers/plans/2026-09-01-dox-agent-context-rollout.md`

## Sources reviewed

Primary/current references:

- Agent Zero DOX repository: <https://github.com/agent0ai/dox>
- Agent Zero DOX explanation: <https://www.agent-zero.ai/p/articles/one-markdown-file-fixes-ai-coding-context/>
- Agent Zero repository: <https://github.com/agent0ai/agent-zero>
- OpenAI harness engineering: <https://openai.com/index/harness-engineering/>
- OpenAI Codex agent-loop instruction loading: <https://openai.com/index/unrolling-the-codex-agent-loop/>
- OpenAI Codex AGENTS.md guidance: <https://openai.com/index/introducing-codex/>
- Anthropic Claude Code memory / CLAUDE.md: <https://code.claude.com/docs/en/memory>
- Gemini CLI GEMINI.md context hierarchy: <https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/gemini-md.md>

These external behaviors can change. The implementation plan includes periodic
verification rather than treating this document as an eternal vendor contract.

## 1. What DOX actually is

Agent Zero's `agent0ai/dox` project is intentionally small. Its core model is:

1. a root `AGENTS.md` contains project-wide rules and a child index;
2. durable subtrees may contain their own `AGENTS.md` files;
3. before editing, an agent walks from the root through the target path and reads
   each applicable contract;
4. the closest contract provides the most local guidance while parent contracts
   retain broader rules;
5. after meaningful work, the agent checks whether the nearest contract/index
   must be updated;
6. documentation should describe stable contracts, not become a diary.

The default child sections in the reference DOX contract are:

- Purpose
- Ownership
- Local Contracts
- Work Guidance
- Verification
- Child DOX Index

DOX has no runtime, package, vector database, or daemon. It is a documentation
and instruction-organization convention.

## 2. Why the idea fits this repository

This project is now large enough that root-only context is inefficient.

Current root operating documents are substantial and cover many unrelated areas:

- PostgreSQL safety;
- ingestion;
- SQLMesh;
- conformance;
- statistics;
- model evaluation;
- source rights;
- testing;
- CLI rules;
- GitHub workflow;
- product/website direction;
- delegation behavior.

An agent fixing a Retrosheet parser should not need every model-promotion rule in
its immediate working context. An agent changing Markov math should not need the
full connector bootstrap contract repeated beside it.

The repository also already has a real documentation-drift example: current root
agent doctrine still refers to a fixed/shared `mlb_test` workflow while the
current README describes per-run isolated pytest databases cloned from a base
connection. A hierarchy does not automatically prevent drift, but it makes
ownership clearer: test execution rules should be owned nearest `tests/`, with the
root containing only the invariant safety rule.

## 3. The strongest outside validation: OpenAI's own harness lesson

OpenAI's 2026 harness-engineering write-up reports that a giant `AGENTS.md`
performed poorly: it consumed scarce context, made every rule look equally
important, became stale, and was hard to verify. Their preferred model is a short
`AGENTS.md` that acts as a map into a structured documentation system.

That is highly compatible with DOX **if we keep DOX concise**.

The synthesis for this project is:

```text
short root AGENTS.md
        |
        +--> child AGENTS.md at real subsystem boundaries
        |
        +--> links to detailed docs/specs/runbooks
        |
        +--> machine-readable/generated contracts where possible
```

Do not turn every child `AGENTS.md` into a second encyclopedia.

## 4. Tool compatibility

### 4.1 Codex

Codex is the cleanest fit.

OpenAI documents that `AGENTS.md` can appear at multiple levels of a repository,
that its scope is the directory tree rooted where the file lives, and that deeper
instructions apply to files in the deeper subtree. Current Codex instruction
loading also supports `AGENTS.override.md` and configurable fallback filenames.

Recommended behavior:

- canonical root and child files are `AGENTS.md`;
- no full `CODEX.md` duplicate is necessary;
- Codex-specific behavior should be kept in user/global Codex config unless it is
  truly a shared repository requirement;
- if a `CODEX.md` file is ever added for human discoverability, it must be a tiny
  pointer and must **not** become another source of project doctrine.

### 4.2 Claude Code

Anthropic explicitly documents that Claude Code reads `CLAUDE.md`, not
`AGENTS.md`. Anthropic also explicitly recommends importing an existing
`AGENTS.md` from `CLAUDE.md` to avoid duplication:

```markdown
@AGENTS.md
```

Claude Code supports hierarchy too. `CLAUDE.md` files above the working directory
load at launch, while nested files can load on demand as Claude reads files in
those subdirectories. Anthropic recommends concise instruction files (roughly
under 200 lines) and using path-scoped rules/skills for more specialized behavior.

Recommended behavior:

- root `CLAUDE.md` imports root `AGENTS.md`;
- root `CLAUDE.md` contains only Claude-specific additions that cannot live in the
  canonical contract;
- at DOX child boundaries, add a tiny `CLAUDE.md` bridge containing
  `@AGENTS.md` only when needed for portable nested behavior;
- alternatively, where a Claude-only path rule is genuinely useful, place it in
  `.claude/rules/` with a path scope instead of duplicating project doctrine;
- keep personal preferences in `~/.claude/CLAUDE.md` / local settings, not the
  repository.

Important: importing root `AGENTS.md` from one root `CLAUDE.md` does not by itself
make all nested child `AGENTS.md` files visible to vanilla Claude Code. Either
nested bridge files, Claude path-scoped rules, or another supported loader is
needed for local DOX context.

### 4.3 Gemini CLI / Gemini agents

Gemini CLI has a hierarchical context system using `GEMINI.md` by default. It
loads global, project/ancestor, and local/JIT context and supports `@file.md`
imports. Current Gemini CLI also allows `context.fileName` to be configured with
multiple names, including `AGENTS.md`.

Recommended behavior for a portable repository:

- root `GEMINI.md` imports `AGENTS.md`;
- child DOX boundaries may have tiny `GEMINI.md` -> `@AGENTS.md` bridges;
- users who control their Gemini configuration may instead configure
  `context.fileName` to include `AGENTS.md`, reducing bridge-file need;
- do not assume every contributor has custom Gemini settings, so repository
  behavior should work with defaults where practical;
- Antigravity/Agy delegation prompts should still be self-contained for bounded
  delegated tasks because agent harnesses differ in exactly which context files
  they pass to subagents.

### 4.4 Agent Zero

Agent Zero is the source of the DOX convention and is naturally compatible with
its own approach. Agent Zero also supports project-scoped memory, skills,
subagents, tools, and host-repository work.

The repository should not become dependent on Agent Zero to use DOX. The value of
DOX is specifically that it remains useful plain Markdown when Agent Zero is not
present.

### 4.5 Other agents

For OpenCode and tools that natively support `AGENTS.md`, use the canonical tree.
For tools that use a different instruction filename, prefer a thin import/pointer
adapter if the tool supports imports. If it does not, generate a small adapter from
canonical contracts rather than hand-maintaining a second doctrine.

## 5. Canonical ownership model

The proposed ownership hierarchy is:

```text
AGENTS.md                         canonical global contract + child index
CLAUDE.md                         @AGENTS.md + Claude-only additions
GEMINI.md                         @AGENTS.md + Gemini-only additions

mlb_baseball/AGENTS.md            Python package/public architecture
mlb_baseball/CLAUDE.md            @AGENTS.md
mlb_baseball/GEMINI.md            @AGENTS.md

mlb_baseball/connectors/AGENTS.md acquisition/source contract
mlb_baseball/sql/AGENTS.md        operational SQL contract
mlb_baseball/model/AGENTS.md      modeling/PIT/evaluation contract (while frozen)
transforms/AGENTS.md              SQLMesh contract
migrations/AGENTS.md              DDL/migration contract
tests/AGENTS.md                   testing/database-isolation contract
docs/AGENTS.md                    documentation/current-vs-historical contract
plans/AGENTS.md                   execution-plan/progress contract
scripts/AGENTS.md                 operational/destructive-script safety contract
```

This is an **initial candidate list**, not an instruction to create all of these
blindly. During rollout, create a child only when the directory is a durable
boundary with meaningfully different rules.

Avoid one `AGENTS.md` per trivial folder. Too many context files would recreate
the same problem in fragmented form.

## 6. What belongs in the root

The root should become much shorter than it is today.

Root-owned invariants should include only things that apply nearly everywhere:

- product mission/current focus;
- source-rights and research-truth principles;
- production database safety invariant;
- point-in-time/leakage honesty;
- preserve existing assets and avoid speculative frameworks;
- measure before rewrite/optimization;
- Git/PR safety;
- required verification discipline;
- child DOX index;
- links to detailed living docs.

Detailed connector, SQL, model, test, and documentation rules should move to the
nearest child contract.

Target: approximately 100–150 lines if that can be achieved without removing
important global rules. This aligns with both DOX's concise style and current
OpenAI/Anthropic guidance favoring smaller persistent context.

## 7. What belongs in child contracts

### `mlb_baseball/AGENTS.md`

Own:

- package dependency direction;
- public facade/backward-compatibility policy;
- typing/dataclass/Protocol guidance;
- pure-domain-vs-DB import boundary;
- naming rules that apply to package code;
- child index for connectors/stats/model/sql/etc.

### `connectors/AGENTS.md`

Own:

- connector `bootstrap`/`update`/health contract;
- source-profile/rights checks;
- raw artifact preservation and replay;
- retry/rate-limit expectations;
- idempotency;
- schema-drift behavior;
- source-specific child indexes only when a source becomes a durable subsystem.

### `tests/AGENTS.md`

Own:

- actual current pytest database-isolation behavior;
- unit vs integration boundaries;
- real PostgreSQL rule;
- offline network fixtures;
- fixture cleanup/rollback rules;
- randomized/parallel-worker requirements once adopted;
- commands that actually verify test changes.

### `transforms/AGENTS.md`

Own:

- SQLMesh model/audit conventions;
- incremental time/grain rules;
- no identity/ML procedural logic;
- tie-out requirements before promotion.

### `migrations/AGENTS.md`

Own:

- forward-only migration rules;
- explicit production-target warning;
- extension policy;
- transactional/non-transactional DDL behavior;
- schema-contract update requirements.

### `docs/AGENTS.md`

Own:

- living vs dated snapshot distinction;
- source/citation expectations;
- map/index ownership;
- when to update docs after code changes;
- generated-vs-hand-authored policy;
- archive rules.

## 8. Tool-specific files must stay thin

### `CLAUDE.md`

Preferred future shape:

```markdown
@AGENTS.md

# Claude Code adapter

- Claude-specific workflow behavior only.
- Use project skills/path-scoped rules for task-specific procedures rather than
  expanding this file.
```

The current `CLAUDE.md` contains valuable doctrine, but much of it duplicates or
overlaps `AGENTS.md`. Rollout should migrate canonical rules rather than deleting
them.

### `GEMINI.md`

Preferred future shape:

```markdown
@AGENTS.md

# Gemini adapter

- Gemini/Agy-specific delegation or verification behavior only, if any.
```

If Gemini is configured to load `AGENTS.md` directly, this bridge can be reduced
or omitted locally; keeping it in-repo still improves default portability.

### `CODEX.md`

Recommendation: **do not create a full repository `CODEX.md`**. Codex already
natively reads the canonical `AGENTS.md` hierarchy. A second full file would be
pure duplication.

If future Codex behavior requires a dedicated adapter, use the documented Codex
fallback/config mechanism and keep the adapter minimal.

## 9. Relationship to skills, runbooks, specs, and memory

DOX is not the correct home for every procedure.

Use:

- `AGENTS.md`: stable, always-relevant contracts for a subtree;
- skills: occasional multi-step procedures that should load on demand;
- runbooks: human/agent operational procedures with substantial detail;
- architecture/docs: durable explanation and rationale;
- dated specs/plans: one change/program's intended work;
- ADRs: why a non-trivial decision was made;
- agent auto-memory: local learned facts/preferences that are not project doctrine;
- generated docs: repeatable reference material derived from code/contracts.

A useful test is:

> Would a competent contributor editing almost any file in this subtree need this
> rule before making a safe change?

If yes, it may belong in `AGENTS.md`. If not, link to a skill/runbook/spec instead.

## 10. Relationship to adjacent `*.dox.md` files

Agent Zero's main repository currently contains many adjacent files such as
`api/health.py.dox.md` and `helpers/git.py.dox.md`. Those are more granular than
the standalone DOX repository's basic root/child contract.

For `mlb-baseball`, do not generate `foo.py.dox.md` beside every module.

Potentially useful cases:

- a highly load-bearing parser with source quirks not obvious from code;
- a complicated public protocol/interface;
- a generated module contract maintained mechanically;
- a legacy gravity-well module during staged decomposition.

Prefer normal module docstrings, typed interfaces, tests, and subtree `AGENTS.md`
for ordinary modules. Adjacent DOX files become another artifact to keep current,
so they need a concrete benefit.

## 11. Context-budget rules

Persistent context is a limited engineering resource.

Rules:

1. root context is a map and invariant set, not an encyclopedia;
2. local details move down the tree;
3. long procedures move to skills/runbooks;
4. detailed current-state reference should live in docs/code and be read on
   demand;
5. avoid repeating a rule verbatim in parent and child unless local repetition is
   necessary for safety;
6. when rules conflict, reconcile/remove stale text rather than adding a third
   explanation of the conflict;
7. generated indexes should be preferred where manual lists repeatedly drift.

## 12. Update contract

After a meaningful code change, the agent should perform a DOX pass, but this
must not turn every one-line edit into documentation churn.

Update the nearest contract when the change modifies a durable:

- responsibility or ownership boundary;
- public/local interface;
- required input/output;
- operational safety rule;
- verification command;
- source/rights contract;
- testing contract;
- architectural dependency direction;
- child context index.

Do not update contracts for purely internal refactors that preserve all described
behavior.

## 13. Verification strategy

Phase 1 should remain Markdown-only and human-reviewable.

After the hierarchy proves useful, consider a tiny validation script that checks:

- every indexed child `AGENTS.md` exists;
- every child has a parent index entry;
- bridge files contain the expected import/pointer and no duplicated large body;
- no obviously conflicting database-name/test-isolation statements remain;
- links to mandatory docs are valid;
- root/child line-size thresholds produce warnings, not arbitrary hard failures.

Do not build a full documentation framework solely to support DOX.

## 14. Cross-project standard

If the MLB pilot succeeds, standardize the pattern for other projects with a
small starter template rather than copying this repository's baseball-specific
content.

Generic template:

```text
AGENTS.md
CLAUDE.md        # imports AGENTS.md + vendor-only rules
GEMINI.md        # imports AGENTS.md + vendor-only rules

docs/
  AGENTS.md
src/
  AGENTS.md
tests/
  AGENTS.md
```

Project templates should define:

- root DOX contract shape;
- thin vendor bridge pattern;
- child section shape;
- index rules;
- verification expectations;
- guidance on skills vs contracts vs runbooks;
- no mandatory runtime dependency.

Do not centralize all project context in a remote mutable file or Git submodule.
Each repository must remain understandable and reproducible at its checked-out
commit. A template repository or update script may help start/reconcile projects,
but project doctrine belongs in the project.

## 15. Risks and mitigations

### Risk: too many files

Mitigation: only create children at durable boundaries. Start with a small pilot.

### Risk: duplicated vendor docs

Mitigation: canonical `AGENTS.md`; thin import adapters only.

### Risk: local rules weaken global safety

Mitigation: root explicitly defines non-overridable invariants (production DB,
source rights, research honesty, Git safety). Children specialize; they do not
relax those invariants.

### Risk: docs become stale anyway

Mitigation: nearest-owner update contract, indexes, code-review checklist, and
later lightweight validation.

### Risk: context becomes larger, not smaller

Mitigation: root reduction is part of rollout; move detail downward/on-demand;
measure actual instruction size after the pilot.

### Risk: different agents resolve precedence differently

Mitigation: avoid intentional parent/child contradictions. More-specific docs
should add operational detail, not redefine global policy. Vendor bridges make
local loading explicit where necessary.

## 16. Recommended decision

**Proceed with a staged DOX pilot in `mlb-baseball`.**

The repository is a particularly good candidate because it has:

- several durable technical subdomains;
- multiple AI coding agents;
- large root instruction files;
- frequent parallel/stacked PR work;
- high data-safety and research-correctness requirements;
- enough accumulated docs that navigation/context quality now matters.

The pilot should be considered successful only if it makes agent work more
focused and reduces contradictory/stale doctrine. File count alone is not a
success metric.

If the pilot succeeds, extract a generic cross-project template and apply the
pattern gradually to other repositories.