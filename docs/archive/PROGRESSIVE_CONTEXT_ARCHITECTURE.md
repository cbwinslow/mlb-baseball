# Progressive context architecture

Status: design clarification, 2026-09-01.

This document clarifies the intended relationship between DOX, `AGENTS.md`,
`CLAUDE.md`, Gemini context files, skills, runbooks, and source-adjacent
`*.dox.md` files.

The central idea is **progressive disclosure through the filesystem**:

> Keep only broadly relevant context at the repository root. Put domain-specific
> context next to the domain that owns it. Put file-specific durable contracts
> next to unusually complex files. Put task procedures in skills/runbooks that
> load only when needed. Keep agent-specific instructions in that agent's native
> mechanism instead of forcing every tool to share identical behavior.

This is the model to use when implementing DOX in this repository and, if the
pilot succeeds, in future projects.

## 1. Two independent dimensions

Do not collapse these into one file hierarchy.

### Dimension A — project/context scope

This answers:

> What part of the repository does this knowledge describe?

Typical levels:

```text
repository-wide
    -> package/domain
        -> subsystem/folder
            -> individual complex file
                -> task-specific procedure
```

Examples:

- root `AGENTS.md`: mission, global safety, project map, current focus;
- `mlb_baseball/connectors/AGENTS.md`: connector-wide acquisition rules;
- `mlb_baseball/connectors/retrosheet.py.dox.md`: exact durable contract for
  the Retrosheet connector;
- `docs/SOURCE_RIGHTS.md`: deep human/reference source-rights explanation;
- a skill/runbook: a multi-step ingestion or release procedure used only when
  that task is performed.

### Dimension B — agent/tool behavior

This answers:

> Is this instruction shared project truth, or behavior specific to one coding
> agent/harness?

Examples:

- `AGENTS.md`: shared/canonical repository context where possible;
- `CLAUDE.md` and `.claude/rules/`: Claude Code-specific behavior and context;
- `GEMINI.md` / Gemini configuration: Gemini-specific behavior and context;
- Codex `AGENTS.md` hierarchy / Codex config: Codex-specific loading or behavior;
- Agent Zero project/profile configuration: Agent Zero-specific behavior.

These dimensions intersect but are not the same thing.

A connector can therefore have both:

```text
connectors/AGENTS.md       shared connector contract
connectors/CLAUDE.md       Claude-only connector instructions, when needed
connectors/GEMINI.md       Gemini-only connector instructions, when needed
retrosheet.py.dox.md       tool-neutral source-adjacent knowledge
```

Do not force `CLAUDE.md` to become only an alias if Claude genuinely needs
special instructions. Likewise, do not copy Claude-only workflow rules into the
canonical project contract merely so every file looks symmetrical.

## 2. Why progressive disclosure saves context

A large repository has far more useful knowledge than any agent needs for one
change.

An agent modifying a Retrosheet parser does not need the full model-promotion
policy, Astro deployment plan, Bayesian modeling notes, or every migration rule
in its immediate context.

Instead, the ideal retrieval path is approximately:

```text
small root context
    -> connector-local context
        -> Retrosheet sidecar
            -> exact relevant tests / rights reference / table contract
```

An agent modifying Markov simulation follows a different path:

```text
small root context
    -> package/model context
        -> simulation/Markov context
            -> exact sidecar/stat definitions/tests
```

This is intentionally similar to skills and other progressive-disclosure
systems: the agent starts with a map and invariants, then loads detail only when
its task makes that detail relevant.

Benefits:

- fewer always-on tokens;
- less irrelevant guidance competing for attention;
- more detailed local documentation without bloating root context;
- better ownership of rules and knowledge;
- easier updates because context lives near the implementation it describes;
- less need to rely on chat history or agent memory;
- easier cross-agent handoff because knowledge is stored in the repository.

## 3. The filesystem becomes the context index

The repository path itself should help route context.

Illustrative MLB structure:

```text
AGENTS.md
CLAUDE.md
GEMINI.md

mlb_baseball/
    AGENTS.md

    connectors/
        AGENTS.md
        CLAUDE.md              # only if Claude-specific local rules exist
        GEMINI.md              # only if Gemini-specific local rules exist

        retrosheet.py
        retrosheet.py.dox.md
        kalshi.py
        kalshi.py.dox.md
        polymarket.py
        polymarket.py.dox.md

    stats/
        AGENTS.md
        batting.py
        batting.py.dox.md      # if file-level DOX adds value
        pitching.py
        pitching.py.dox.md

    research/
        AGENTS.md

    model/
        AGENTS.md
        CLAUDE.md              # possible model-review/planning behavior for Claude

transforms/
    AGENTS.md

migrations/
    AGENTS.md

tests/
    AGENTS.md
    CLAUDE.md                  # only if Claude needs testing-specific behavior

docs/
    AGENTS.md

.claude/
    rules/
        testing.md             # Claude-only path-scoped rules if justified
        migrations.md
    skills/
        ...                    # task-specific Claude procedures
```

The exact tree should follow durable repository boundaries rather than this
example mechanically.

## 4. Root context should be deliberately incomplete

A good root context does **not** try to teach the agent the whole project.

It should contain enough to answer:

1. What is this project?
2. What are the global invariants that must never be violated?
3. What is currently in scope?
4. Where is the more specific context for the area I am touching?
5. What is the global definition of safe/verified work?

Everything else should be routed downward or loaded on demand.

The root therefore acts more like an index/router than an encyclopedia.

For this project, likely root topics are:

- research database is the current product focus;
- PostgreSQL is authoritative;
- production-data safety;
- source-rights/provenance honesty;
- point-in-time/leakage honesty;
- preserve and reuse existing assets before adding new frameworks;
- measure before rewrites/optimizations;
- Git/PR safety;
- high-level verification expectations;
- Child DOX Index and links to current sources of truth.

Connector implementation details, SQLMesh rules, test fixture rules, model
promotion thresholds, and documentation-history conventions should not remain in
root simply because they are important. They are important **locally**.

## 5. Folder-level `AGENTS.md` is contextual routing + local contract

A folder-level DOX file should explain the stable things an agent needs before
working anywhere in that subtree.

Example `connectors/AGENTS.md` responsibilities:

- what connectors own;
- bootstrap/update/backfill interface;
- source-rights/profile enforcement;
- artifact/provenance requirements;
- retry/rate-limit policy;
- idempotency;
- raw/source-faithful naming;
- health checks;
- schema-drift behavior;
- relationship to conformance;
- exact verification expectations;
- whether this directory is a file-documented DOX profile;
- Child DOX Index for any genuinely large connector subpackages.

It should **not** repeat every Retrosheet, MLB API, Kalshi, and Polymarket quirk.
Those belong closer to those implementations.

## 6. Source-adjacent `*.dox.md` is file-level progressive disclosure

This is especially valuable for source files whose contract is much richer than
what a normal docstring should carry.

For example:

```text
mlb_api.py
mlb_api.py.dox.md
```

The Python file owns executable behavior.

The sidecar can own durable engineering knowledge such as:

- purpose/responsibility boundary;
- public classes/functions/protocols;
- upstream API families;
- request/retry/session assumptions;
- persisted raw tables/artifacts;
- IDs and grains;
- source-specific quirks;
- side effects;
- important dependencies and downstream consumers;
- invariants that are easy to break accidentally;
- exact relevant tests and health checks;
- references to deep docs rather than duplicating them.

A sidecar should be read when the source file is about to be changed, not injected
into every session.

That is where DOX gains token efficiency: we can afford **more total documented
context** because only a relevant slice is loaded for a given task.

## 7. `CLAUDE.md` is not merely a bridge

Claude Code has its own native instruction system and some instructions are
legitimately Claude-specific.

The correct rule is:

> Reuse shared project facts from DOX, but preserve first-class Claude-specific
> instructions in Claude's own hierarchy.

A root `CLAUDE.md` may therefore look conceptually like:

```markdown
@AGENTS.md

# Claude Code-specific repository behavior

- Claude-specific planning or review expectations.
- Claude tool/hook requirements.
- Claude-specific subagent usage rules.
- Rules for when to use Claude skills or plan mode.
- Claude-specific MCP/plugin behavior.
```

That is **not duplication** if those rules genuinely apply only to Claude.

Likewise, a nested folder can have its own `CLAUDE.md` when local Claude behavior
is useful. Claude Code currently loads parent `CLAUDE.md` files and discovers
nested files on demand as it reads files in those subdirectories, which naturally
supports filesystem-based progressive disclosure.

Claude also provides `.claude/rules/` with path-scoped rules. Those are ideal for
instructions like:

```text
When touching migrations/**, perform Claude-specific safety/review workflow X.
When touching tests/**, use Claude-specific test-triage behavior Y.
```

They should not be used to duplicate the general migrations/testing contract.

### Claude content categories

Use:

- `CLAUDE.md`: Claude-specific persistent instructions at that filesystem scope;
- `.claude/rules/`: modular/path-conditional Claude instructions;
- Claude skills: multi-step or occasional procedures loaded only when relevant;
- `AGENTS.md` / DOX sidecars: shared project/domain/file knowledge Claude should
  also consult;
- Claude auto-memory/local files: personal learned preferences, not canonical
  team doctrine.

This distinction should remain explicit in the rollout.

## 8. Codex fits the shared hierarchy directly

Codex natively treats `AGENTS.md` files as scoped instructions: an `AGENTS.md`
applies to the directory tree below it and more deeply nested instructions apply
more specifically.

That makes the DOX tree a natural Codex progressive-disclosure mechanism.

Codex-specific requirements should still be allowed when needed through Codex's
supported configuration/instruction mechanisms. The rule is only that we should
not invent a full duplicate `CODEX.md` doctrine when Codex already understands
our canonical scoped `AGENTS.md` tree.

## 9. Gemini has its own progressive-disclosure system too

Gemini CLI's native context system is also hierarchical. Current Gemini CLI can
load project/ancestor context and just-in-time context when tools access files or
directories. It also supports multiple configured context filenames, including
`AGENTS.md`.

Therefore Gemini can participate in the same filesystem architecture while still
retaining Gemini-specific instructions where useful.

Possible approaches:

- configure Gemini to recognize both `AGENTS.md` and `GEMINI.md`;
- keep `GEMINI.md` for genuinely Gemini-specific behavior;
- use nested/JIT Gemini context at durable subsystem boundaries;
- let DOX sidecars remain neutral files that Gemini reads when routed to them.

As with Claude, do not erase Gemini-specific strengths merely to force one common
filename.

## 10. Skills are the procedural layer

A recurring mistake in agent documentation is putting every workflow into the
persistent instructions.

Instead:

```text
persistent/root context     -> invariants + map
folder context              -> local contracts
file sidecar                -> exact implementation knowledge
skill/runbook               -> procedure
active task/plan            -> current objective
```

Examples of things better suited to skills/runbooks than `AGENTS.md`:

- how to release a version;
- how to perform a large historical backfill;
- how to validate a sabermetric formula against external references;
- how to conduct a dependency/library replacement spike;
- how to triage a failed production ingestion;
- how to run the full model-promotion review.

These procedures may be detailed because they are not loaded for unrelated work.

This is the same progressive-disclosure principle applied to process knowledge.

## 11. Deep human docs remain important

DOX should route to authoritative human/reference documentation rather than
trying to replace it.

Examples:

```text
connectors/retrosheet.py.dox.md
    -> docs/SOURCE_RIGHTS.md
    -> docs/DATA_SOURCES.md
    -> docs/TABLE_CONTRACTS.md

stats/batting.py.dox.md
    -> machine-readable Stat Registry
    -> formula citation
    -> external validation report
```

The sidecar summarizes what an editing agent must know and points to deep evidence
when more detail is required.

This avoids two bad extremes:

1. one giant prompt file containing the whole project;
2. sidecars duplicating the whole documentation corpus.

## 12. Example: context loaded for a Retrosheet connector change

A capable agent should approximately follow:

```text
1. root AGENTS.md
   - global project/safety/product context

2. mlb_baseball/AGENTS.md
   - package architecture and dependency rules

3. mlb_baseball/connectors/AGENTS.md
   - connector contract and file-level DOX policy

4. retrosheet.py.dox.md
   - exact source/file contract and verification map

5. retrosheet.py
   - implementation

6. exact referenced tests/docs
   - only those needed for this change

7. relevant skill/runbook
   - only if the task is a special procedure such as backfill/release
```

For Claude, the applicable `CLAUDE.md` / path rules are layered into the same task
because they describe **how Claude should work**, not what Retrosheet means.

## 13. Example: context loaded for a documentation edit

```text
root AGENTS.md
    -> docs/AGENTS.md
        -> target living doc / dated spec
```

No connector details, model promotion rules, or migration procedures need to be
injected unless the documentation task explicitly touches those topics.

## 14. Avoid over-documenting every file

Progressive disclosure does not imply one sidecar for every file in the
repository.

Use file-level DOX when at least one is true:

- the file is a durable public/component boundary;
- important contracts cannot be inferred safely from the code alone;
- the file integrates multiple external systems;
- source quirks or invariants are easy to break;
- the file is large enough that understanding it repeatedly wastes substantial
  agent context;
- the module has meaningful side effects or security/data-safety behavior;
- the directory explicitly chooses a file-documented DOX profile, as Agent Zero
  does for APIs/helpers/tools.

Do not require sidecars for trivial modules, generated files, one-line migration
files, or every test unless evidence shows that adds value.

## 15. Context-budget principle

The objective is not fewer Markdown files. It is **less irrelevant Markdown per
agent task**.

A repository may eventually contain more total documentation while using fewer
context tokens per change.

That is a feature, not a contradiction.

A useful optimization target is:

```text
maximum durable knowledge in the repository
minimum irrelevant knowledge loaded for a specific task
```

This should guide every decision about root docs, local context, sidecars, skills,
and agent-specific files.

## 16. Implementation implications for this repository

Update the current DOX rollout with these principles:

1. Preserve Claude-specific instructions instead of treating `CLAUDE.md` as a
   disposable duplicate of `AGENTS.md`.
2. Classify every current root rule by both **filesystem scope** and **agent
   scope** before moving it.
3. Shrink root files by pushing domain context to the owning folders.
4. Use folder `AGENTS.md` files as local contracts and routing indexes.
5. Pilot file-documented DOX where it provides high information value, beginning
   with connectors and selected gravity-well modules.
6. Use nested `CLAUDE.md` / `.claude/rules` for genuinely Claude-specific local
   behavior.
7. Use Gemini's own hierarchical/JIT context while sharing neutral DOX knowledge.
8. Keep task procedures in skills/runbooks rather than always-on context.
9. Add structural checks only after the intended coverage/profile rules are
   stable.
10. Measure the pilot by context relevance, instruction drift, agent edit
    accuracy, and maintenance burden—not by the number of DOX files created.

## 17. Cross-project standard if the pilot succeeds

The reusable standard should be a **context architecture**, not a single copied
`AGENTS.md` template.

Generic concept:

```text
root shared contract
root agent-specific contracts

src-or-package/
    local shared contract
    optional local agent-specific contract
    important-file.ext.dox.md

tests/
    local shared contract

docs/
    local shared contract

agent-native rules/
agent-native skills/
shared runbooks/
```

Each project then chooses its own durable boundaries and file-documented profiles.

The success condition is that an unfamiliar agent can start with very little
context, follow the filesystem to progressively discover exactly the knowledge it
needs, and make a safe change without loading the entire project's institutional
memory into every prompt.
