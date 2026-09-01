# Agent context architecture

Status: proposed durable design for owner review, 2026-09-01.

This document evaluates Agent Zero's DOX approach and adapts it to this repository's
real multi-agent workflow: OpenAI Codex, Claude Code, Gemini CLI / Antigravity-style
Gemini agents, Agent Zero, and similar coding agents.

The governing principle is **progressive disclosure through the filesystem**:
keep global context small, put domain context next to the domain that owns it,
put unusually rich file contracts in source-adjacent `*.dox.md` files, and keep
procedures in skills/runbooks that load only when needed.

A second, independent principle is **agent-specific behavior stays first class**.
`CLAUDE.md`, `.claude/rules/`, Gemini context, Codex configuration, and Agent Zero
profiles may contain instructions that genuinely apply only to that harness. They
must not be flattened into one supposedly universal file merely for symmetry.

See also `docs/PROGRESSIVE_CONTEXT_ARCHITECTURE.md`, which is the clearest
statement of this model and should control if older wording in this file appears
to imply that tool-specific files are only aliases.

## Decision summary

Adopt DOX as a recursively indexed, filesystem-native context architecture:

1. root `AGENTS.md` contains only repository-wide invariants, current focus, and
   a Child DOX Index;
2. child `AGENTS.md` files own stable context for durable subtrees;
3. a child may declare its directory a **file-documented DOX profile**, meaning
   selected or all direct implementation files require matching
   `<source>.dox.md` sidecars;
4. those sidecars own durable knowledge about the exact implementation's
   responsibilities, interfaces, side effects, dependencies, known quirks, and
   verification;
5. skills/runbooks own detailed procedures that should not consume persistent
   context for unrelated work;
6. human/reference docs, registries, ADRs, and tests remain authoritative deep
   evidence and are linked rather than copied into every context file;
7. tool-specific instruction systems remain independent where they have genuinely
   tool-specific behavior.

The desired optimization target is:

> maximum durable project knowledge stored in the repository, with minimum
> irrelevant knowledge loaded for any one task.

## Sources reviewed

Primary/current references:

- Agent Zero DOX repository: <https://github.com/agent0ai/dox>
- Agent Zero repository: <https://github.com/agent0ai/agent-zero>
- Agent Zero root and subtree `AGENTS.md` contracts and current `*.py.dox.md`
  sidecars;
- OpenAI Codex AGENTS.md/context-loading guidance;
- Anthropic Claude Code memory, nested `CLAUDE.md`, `.claude/rules`, imports,
  and skills guidance;
- Gemini CLI hierarchical/JIT context and configurable context filenames.

External tool behavior changes over time. Verify current vendor behavior during
implementation instead of treating this document as permanent vendor API truth.

## 1. What DOX means here

The standalone `agent0ai/dox` repository establishes a small recursive contract:

- root `AGENTS.md` owns project-wide instructions and a child index;
- child `AGENTS.md` files own local instructions for durable boundaries;
- before editing, an agent walks the applicable path and reads the contracts;
- closer context is more specific while parent invariants continue to apply;
- meaningful changes trigger a DOX pass so affected contracts and indexes remain
  current;
- docs describe stable contracts rather than acting as diaries.

Agent Zero's production repository demonstrates the more powerful large-project
application: several directories are explicitly declared **file-documented DOX
profiles**. Their local `AGENTS.md` files require matching same-directory
`*.py.dox.md` files for direct implementation modules.

A representative sidecar has sections such as:

- Purpose
- Ownership
- Runtime/Local Contracts
- Key Concepts
- Work Guidance
- Verification
- Child DOX Index

The source file owns executable behavior. The sidecar owns durable context about
that behavior.

This is not just prompt organization. It is source-adjacent institutional memory
routed through filesystem scope.

## 2. Two orthogonal dimensions

Every instruction/context item should be classified along two axes.

### 2.1 Filesystem/project scope

Where does this knowledge apply?

```text
repository
  -> package/domain
    -> subsystem/folder
      -> exact implementation file
        -> occasional task/procedure
```

### 2.2 Agent/harness scope

Who should follow this behavior?

```text
shared project context
Claude-specific behavior
Codex-specific behavior
Gemini-specific behavior
Agent Zero-specific behavior
human/operator-only procedure
```

These must not be confused.

For example, `connectors/AGENTS.md` can describe connector invariants shared by
all agents while `connectors/CLAUDE.md` or a path-scoped `.claude/rules/` entry
can impose an additional Claude-only review workflow in that directory.

Likewise, `retrosheet.py.dox.md` should remain neutral implementation knowledge
that any capable agent can read when working on that file.

## 3. Why this fits mlb-baseball

This repository now contains more useful institutional knowledge than should be
loaded into every coding session:

- PostgreSQL safety;
- source rights and provenance;
- acquisition/retry/idempotency rules;
- cross-source identity resolution;
- SQLMesh transformation contracts;
- test database isolation;
- sabermetric formula validation;
- prediction point-in-time constraints;
- model promotion/evaluation rules;
- documentation/history rules;
- operational scripts;
- future website/market work.

An agent changing one Retrosheet parser needs only a small subset. An agent
changing Markov math needs a different subset.

The repository therefore benefits from more total documented context **spread
through the filesystem**, so the relevant slice can be loaded progressively.

## 4. Desired retrieval behavior

For a Retrosheet connector change:

```text
root AGENTS.md
    -> mlb_baseball/AGENTS.md
        -> connectors/AGENTS.md
            -> retrosheet.py.dox.md
                -> retrosheet.py
                    -> exact tests / rights / table references needed
```

For a Markov change:

```text
root AGENTS.md
    -> mlb_baseball/AGENTS.md
        -> model/AGENTS.md
            -> Markov-local context/sidecar if present
                -> exact stats/tests/research references
```

The agent should not preload the unrelated branch of the repository knowledge
tree.

This is conceptually the same advantage as skills/progressive disclosure: start
with a compact map, then pull detail only when the task makes it relevant.

## 5. Root `AGENTS.md`

Root should intentionally be incomplete.

It owns only near-universal information such as:

- current product mission/focus;
- PostgreSQL authority and production-data safety;
- source-rights/provenance honesty;
- point-in-time/leakage honesty;
- preserve/reuse existing assets before adding frameworks;
- measure before optimization or rewrite;
- Git/PR safety;
- repository-wide verification philosophy;
- Child DOX Index and links to current sources of truth.

It should not contain full connector procedures, SQLMesh authoring detail, pytest
fixture mechanics, or model-promotion rules simply because those things are
important. Their importance is local.

## 6. Folder-level DOX

A folder `AGENTS.md` combines two jobs:

1. local stable contract;
2. router/index to deeper context.

Example `mlb_baseball/connectors/AGENTS.md` should own:

- connector interface expectations;
- rights/profile enforcement;
- source artifact/replay expectations;
- retry/rate-limit conventions;
- idempotency and schema-drift policy;
- raw/source-faithful naming;
- health checks;
- relationship to conformance;
- exact local verification expectations;
- declaration of any file-documented DOX profile;
- child indexes for genuinely large source subpackages.

It should not duplicate every source's quirks.

## 7. File-documented DOX

File sidecars are the key progressive-disclosure extension demonstrated in Agent
Zero.

High-value candidates in this repository include:

- acquisition connectors;
- `conform.py` while it remains a gravity well;
- `cli.py` during staged decomposition;
- `load.py`;
- `report.py`;
- future canonical `stats/*.py` modules where formulas/contracts are rich;
- other public or high-side-effect modules with non-obvious invariants.

Example connector sidecar responsibilities:

```text
Purpose
Ownership
Public/Runtime Contracts
Source and Rights Contracts
IDs and Grains
Artifacts and Side Effects
Important Dependencies
Downstream Consumers
Known Source Quirks
Work Guidance
Verification
References
```

Do not force sidecars onto trivial modules, generated files, every migration, or
every test unless evidence shows that profile is useful.

## 8. Claude Code is first-class, not an alias

This is an explicit correction to an earlier overly simple recommendation.

Claude Code has native mechanisms with semantics that are not identical to Codex
or Gemini. `CLAUDE.md` may and should contain genuinely Claude-specific rules.

Shared project context can be imported from `AGENTS.md`, but that does **not** mean
`CLAUDE.md` should contain nothing else.

Claude-specific content can include:

- when Claude should use plan mode;
- Claude-specific subagent/delegation rules;
- Claude skills that should be preferred for particular tasks;
- Claude hooks/tool safety;
- Claude-specific MCP/plugin behavior;
- Claude review/verification workflow;
- Claude-specific communication or planning requirements;
- anything learned from repeated Claude failure modes that should not constrain
  other agents.

Claude currently supports several progressive-disclosure layers:

- root/project `CLAUDE.md`;
- nested `CLAUDE.md` files discovered on demand as Claude reads subdirectory
  files;
- `.claude/rules/` with path-scoped rules that load for matching files;
- skills for procedures that should load only when invoked/relevant;
- local/user/auto-memory for non-canonical personal knowledge.

Therefore the Claude architecture should look more like:

```text
shared DOX tree                  Claude-specific tree
-----------------------------    -----------------------------
AGENTS.md                         CLAUDE.md
mlb_baseball/AGENTS.md            mlb_baseball/CLAUDE.md (if needed)
connectors/AGENTS.md              connectors/CLAUDE.md (if needed)
retrosheet.py.dox.md              .claude/rules/... (when path-specific)
                                  .claude/skills/... (procedural)
```

These layers cooperate; neither replaces the other.

## 9. Codex

Codex is naturally compatible with canonical filesystem-scoped `AGENTS.md`.
Codex treats an `AGENTS.md` as applying to the directory tree beneath it and more
specific nested instructions apply to deeper paths.

That makes the shared DOX hierarchy a strong Codex context router.

Codex-specific behavior is still allowed through supported Codex configuration or
instruction mechanisms when needed. The design simply avoids inventing a second
full `CODEX.md` copy of shared doctrine when Codex already understands the
canonical tree.

## 10. Gemini / Agy

Gemini CLI also supports hierarchical context and just-in-time local context when
files/directories are accessed. It can use `GEMINI.md` and can be configured with
multiple context filenames including `AGENTS.md`.

So Gemini should:

- consume shared DOX knowledge;
- retain Gemini-specific `GEMINI.md` instructions where useful;
- use its native JIT/hierarchical behavior for local context;
- use Gemini/Agy-specific delegation rules when they differ from Claude/Codex;
- read neutral source-adjacent sidecars when routed to them.

Do not make repository correctness depend on every user having identical global
Gemini settings; keep the repository portable.

## 11. Skills and runbooks are another progressive-disclosure layer

Persistent context should explain contracts, not every procedure.

Use this layering:

```text
root context        invariants + map
folder context      local stable contracts
file sidecar        exact implementation knowledge
skill/runbook       detailed procedure
active plan         current objective/change sequence
```

Examples better suited to skills/runbooks:

- performing a full historical backfill;
- validating a sabermetric formula against external references;
- releasing a versioned dataset;
- conducting an acquisition-library parity spike;
- triaging a production ingestion failure;
- performing model promotion review.

This mirrors Claude's own current guidance: keep always-on context concise, use
path-scoped rules for local instructions, and use skills for task-specific
multi-step procedures.

## 12. Human/reference docs and machine-readable registries

DOX should summarize and route; it should not replace evidence.

For example:

```text
retrosheet.py.dox.md
    -> docs/SOURCE_RIGHTS.md
    -> docs/DATA_SOURCES.md
    -> docs/TABLE_CONTRACTS.md
    -> exact integration tests
```

A future `stats/batting.py.dox.md` should route to:

- the machine-readable Stat Registry;
- authoritative formula citations;
- coverage metadata;
- hand-calculated fixtures;
- external tie-out evidence.

This is how DOX and the planned Stat Registry reinforce each other.

## 13. Proposed MLB filesystem context tree

Illustrative, not mechanical:

```text
AGENTS.md
CLAUDE.md
GEMINI.md

mlb_baseball/
    AGENTS.md

    connectors/
        AGENTS.md
        CLAUDE.md              # only with real Claude-local requirements
        GEMINI.md              # only with real Gemini-local requirements
        retrosheet.py
        retrosheet.py.dox.md
        mlb_api.py
        mlb_api.py.dox.md
        kalshi.py
        kalshi.py.dox.md
        polymarket.py
        polymarket.py.dox.md

    stats/
        AGENTS.md
        batting.py
        batting.py.dox.md      # when worth the maintenance cost
        pitching.py
        pitching.py.dox.md

    research/
        AGENTS.md

    model/
        AGENTS.md
        CLAUDE.md              # possible Claude-only model workflow

transforms/
    AGENTS.md

migrations/
    AGENTS.md

tests/
    AGENTS.md
    CLAUDE.md                  # only if Claude-specific test rules exist

docs/
    AGENTS.md

.claude/
    rules/
    skills/
```

## 14. Context budget and duplication rules

The success metric is not number of files.

Prefer:

> more total durable knowledge in the repository, less irrelevant knowledge in a
> specific agent context window.

Rules:

1. root files stay compact;
2. local knowledge moves to owning folders;
3. implementation knowledge moves to selected sidecars;
4. procedures move to skills/runbooks;
5. agent-specific behavior stays in native agent files;
6. shared facts are not copied independently into Claude/Codex/Gemini files;
7. tool-specific rules are not forced into universal files;
8. deep explanations are linked, not repeated;
9. stale/contradictory context is removed, not explained with more context;
10. structural validation is added only after profiles are stable.

## 15. Implementation consequence

The DOX rollout must classify existing instructions by **both** scope dimensions
before moving them:

| Instruction | Filesystem scope | Agent scope | Destination |
| --- | --- | --- | --- |
| production DB safety | repository | shared | root `AGENTS.md` |
| connector idempotency | connectors | shared | `connectors/AGENTS.md` |
| Retrosheet event quirks | Retrosheet module | shared | `retrosheet.py.dox.md` |
| use Claude plan mode for risky schema edits | migrations | Claude | nested `CLAUDE.md` or `.claude/rules` |
| Gemini delegation handoff format | delegated work | Gemini/Agy | Gemini-specific context/skill |
| release public-safe dataset | task procedure | shared/operator | skill/runbook |
| wOBA formula definition | stat domain | machine truth | Stat Registry + reference docs |

This classification should replace the simpler assumption that all durable rules
must eventually migrate into `AGENTS.md`.

## 16. Rollout principle

Start small enough to verify behavior, but design for real progressive disclosure:

1. audit current rules and identify contradictions;
2. classify them by filesystem scope and agent scope;
3. shrink root shared context;
4. create the first local shared contract (`tests/AGENTS.md` is still a good
   contradiction-resolution pilot);
5. preserve/move Claude-specific rules into Claude-native scoped mechanisms;
6. establish `connectors/` as the first file-documented DOX profile;
7. create high-value connector sidecars from verified code/tests/docs;
8. pilot gravity-well sidecars such as `conform.py.dox.md`;
9. measure actual context usefulness and maintenance burden across Codex, Claude,
   Gemini/Agy, and Agent Zero;
10. only then expand the pattern or standardize it across other repositories.

The objective is not to make every agent consume identical instructions. It is to
make every agent able to **progressively discover the same project truth while
also receiving the specialized instructions that make that particular harness
work well**.
