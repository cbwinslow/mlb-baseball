# DOX protocol and multi-agent context architecture

Status: proposed durable design for owner review, 2026-09-01.

This document corrects the earlier interpretation of Agent Zero's DOX system and
adapts the actual protocol to this repository. The key point is that DOX is not
merely a collection of nested `AGENTS.md` instruction files. It is a recursively
indexed, source-adjacent documentation protocol for giving software agents
just-in-time knowledge about the exact part of a repository they are about to
change.

The implementation plan lives in:

- `docs/superpowers/plans/2026-09-01-dox-agent-context-rollout.md`

## Decision summary

Adopt DOX as a first-class repository knowledge architecture.

Use three layers:

1. **Directory DOX (`AGENTS.md`)** — project/subtree purpose, ownership, local
   contracts, work guidance, verification, and a recursive Child DOX Index.
2. **File DOX (`<source-file>.dox.md`)** — durable source-adjacent contracts for
   files in directories that explicitly opt into a file-documented DOX profile.
3. **Human/reference docs** — architecture, research, runbooks, ADRs, plans, and
   user documentation that DOX indexes or links rather than duplicating.

Tool-specific instruction files (`CLAUDE.md`, `GEMINI.md`) should bridge into the
canonical DOX system instead of becoming parallel copies of project knowledge.
Codex should consume `AGENTS.md` directly rather than receive a duplicate
`CODEX.md` doctrine.

The goal is a repository that explains itself recursively from root -> subsystem
-> exact source file, with each level owning only the information appropriate to
that scope.

## Primary sources reviewed

- Agent Zero DOX repository: <https://github.com/agent0ai/dox>
- Agent Zero repository: <https://github.com/agent0ai/agent-zero>
- Agent Zero root and child `AGENTS.md` DOX trees
- Agent Zero file-level `*.dox.md` profiles under `api/`, `helpers/`, and `tools/`
- OpenAI Codex `AGENTS.md`/harness documentation
- Anthropic Claude Code memory/instruction documentation
- Gemini CLI hierarchical context documentation

The standalone `agent0ai/dox` repository is intentionally tiny. Its canonical
`AGENTS.md` defines the recursive contract. Agent Zero's main repository shows
what that protocol looks like when applied to a large real codebase, including
file-level DOX profiles.

# 1. What DOX actually is

DOX is best understood as **filesystem-addressed just-in-time context**.

It turns the repository tree itself into the retrieval structure:

```text
repository
│
├── AGENTS.md                    global DOX contract + index
│
├── subsystem/
│   ├── AGENTS.md                subsystem DOX contract + index
│   ├── service.py
│   ├── service.py.dox.md        exact contract for service.py
│   ├── parser.py
│   └── parser.py.dox.md
│
└── other-subsystem/
    ├── AGENTS.md
    └── ...
```

When an agent needs to change `subsystem/service.py`, it does not need to ingest
all repository documentation. It follows the path:

```text
root AGENTS.md
       ↓
subsystem/AGENTS.md
       ↓
subsystem/service.py.dox.md
       ↓
source + relevant tests/reference docs
```

This is a lightweight retrieval system implemented entirely with Markdown and
filesystem structure.

## 1.1 The root contract

The root `AGENTS.md` owns:

- project-wide purpose and invariants;
- global safety and quality rules;
- root-owned files/concepts;
- the DOX workflow itself;
- the top-level Child DOX Index.

Agent Zero's root DOX is intentionally an index into direct child contracts such
as `api/AGENTS.md`, `helpers/AGENTS.md`, `plugins/AGENTS.md`, `tests/AGENTS.md`,
and `tools/AGENTS.md` rather than a giant source manual.

## 1.2 Child directory contracts

A child `AGENTS.md` owns a durable subtree boundary.

The reference shape is:

- Purpose
- Ownership
- Local Contracts
- Work Guidance
- Verification
- Child DOX Index

A child may itself index deeper children. The result is recursive, not a single
flat root index.

The closest applicable DOX controls local details while parent contracts remain
binding for broader invariants.

## 1.3 File-level DOX profiles

This is the part the earlier review understated.

Agent Zero deliberately declares some directories to be **file-documented DOX
profiles**. In `api/`, `helpers/`, and `tools/`, the local `AGENTS.md` requires
every direct Python implementation file to have a same-directory sidecar formed
by appending `.dox.md` to the complete filename:

```text
health.py
health.py.dox.md

git.py
git.py.dox.md
```

The source file owns implementation. The sidecar owns durable knowledge about
that implementation.

A typical file-level DOX contains:

```text
# <filename> DOX

## Purpose
## Ownership
## Runtime / Local Contracts
## Key Concepts
## Work Guidance
## Verification
## Child DOX Index
```

Depending on the domain, the contract can record:

- public classes/functions;
- request/response contracts;
- data grain and keys;
- authentication/security assumptions;
- source/rights assumptions;
- side effects;
- persistence behavior;
- important dependencies/callers;
- point-in-time semantics;
- invariants and failure modes;
- tests/commands that verify behavior.

The local directory `AGENTS.md` determines whether sidecars are required. They are
not a universal requirement for every file in every repository.

That distinction is important: DOX supports both coarse directory contracts and
fine file contracts without forcing the fine-grained form where it adds no value.

# 2. The DOX lifecycle

DOX is not static documentation generated once.

## Before editing

An agent should:

1. read root `AGENTS.md`;
2. identify the paths it expects to touch;
3. walk the DOX chain from root to each path;
4. read every applicable child `AGENTS.md`;
5. if the local directory is a file-documented profile, read the matching
   `<file>.dox.md` sidecar;
6. follow links to detailed docs/tests only when relevant;
7. inspect the actual source before changing it.

## While editing

The agent uses the nearest DOX as the contract for:

- what the component owns;
- what must remain compatible;
- what may have side effects;
- what other files must change with it;
- how the change must be verified.

## After editing

The agent performs a DOX pass:

1. update a sidecar if the file's durable contract changed;
2. update the nearest `AGENTS.md` if ownership/workflow changed;
3. update parent Child DOX Indexes if files/boundaries moved or were added;
4. remove stale entries after deletes/renames;
5. run the stated verification;
6. report documentation deliberately unchanged when contracts were preserved.

This gives documentation a concrete ownership/update trigger rather than relying
on someone remembering to update a remote architecture page later.

# 3. Why DOX is more than agent instructions

Calling DOX only an `AGENTS.md` organization pattern misses its strongest value.

It creates a **distributed project knowledge graph encoded in the filesystem**.

The edges are simple and inspectable:

```text
parent directory
   └─indexes→ child directory
                └─owns→ source file
                          └─documented-by→ file.dox.md
                                           └─points-to→ tests/docs/dependencies
```

This helps both humans and agents answer:

- What does this folder own?
- What does this file own?
- What assumptions may I not break?
- What calls this?
- What does it depend on?
- What data/source/grain/time semantics apply?
- Which tests prove the contract?
- Where is deeper rationale documented?

It is closer to a lightweight repository-native knowledge base than a prompt
file.

# 4. Why it fits `mlb-baseball`

This repository is unusually well suited to DOX because many files contain
knowledge that cannot safely be reconstructed from syntax alone.

Examples include:

- source quirks and schema anomalies;
- Retrosheet/Chadwick field interpretation;
- MLB API endpoint/replay behavior;
- cross-source identity rules;
- table grain and point-in-time semantics;
- source-rights restrictions;
- statistical formula provenance;
- market observation timing;
- test database/fixture safety;
- migration and operational safety.

Today much of that knowledge is distributed across code comments, root agent
instructions, ADRs, plans, tests, and large docs. DOX gives each durable concept a
local address without requiring every detail to be duplicated into the sidecar.

A sidecar should summarize the operational contract and point to authoritative
long-form material when needed.

# 5. Proposed MLB DOX topology

A mature target might look like this:

```text
AGENTS.md
│
├── mlb_baseball/
│   ├── AGENTS.md
│   │
│   ├── connectors/
│   │   ├── AGENTS.md             file-documented profile
│   │   ├── mlb_api.py
│   │   ├── mlb_api.py.dox.md
│   │   ├── retrosheet.py
│   │   ├── retrosheet.py.dox.md
│   │   ├── kalshi.py
│   │   ├── kalshi.py.dox.md
│   │   └── ...
│   │
│   ├── stats/
│   │   ├── AGENTS.md             likely file-documented profile
│   │   ├── batting.py
│   │   ├── batting.py.dox.md
│   │   └── ...
│   │
│   ├── research/
│   │   ├── AGENTS.md             query/API semantics
│   │   └── ...
│   │
│   ├── model/
│   │   ├── AGENTS.md
│   │   └── ...                   migrate to finer domains deliberately
│   │
│   └── sql/
│       └── AGENTS.md
│
├── transforms/
│   └── AGENTS.md
│
├── migrations/
│   └── AGENTS.md
│
├── tests/
│   └── AGENTS.md
│
├── docs/
│   └── AGENTS.md
│
├── plans/
│   └── AGENTS.md
│
└── scripts/
    └── AGENTS.md
```

This is a target topology, not permission to create every file mechanically in a
single PR.

# 6. Where file-level DOX is high-value in this project

## 6.1 Connectors — strong candidate for full coverage

`mlb_baseball/connectors/` is analogous to Agent Zero's `api/` directory: it is a
flat set of independent externally-facing adapters with distinct contracts.

I recommend eventually declaring it a file-documented DOX profile.

Each connector sidecar can record:

- upstream source/API;
- source rights/profile;
- bootstrap/update/backfill capabilities;
- artifact/replay behavior;
- raw tables owned;
- natural scope/key;
- retry/rate-limit behavior;
- schema drift/null behavior;
- health checks;
- integration tests;
- known historical/source quirks.

That would be extremely useful to agents touching acquisition code.

## 6.2 Large gravity-well modules — strong transitional use

Files such as current `cli.py`, `conform.py`, and `connectors/mlb_api.py` can
benefit from sidecars while they are being decomposed.

A sidecar can give an agent a fast map of responsibilities and constraints before
it enters thousands of lines of source.

As the file is split, its DOX can be split/moved with the implementation. That
makes DOX useful during refactors rather than creating a stale monument to the old
path.

## 6.3 Stable statistics — strong future use

The proposed neutral `stats/` package should likely be file-documented because
statistical contracts contain more than signatures:

- formula/version;
- required inputs;
- grain;
- unit;
- null policy;
- historical coverage;
- PIT classification;
- citations;
- tie-out tests.

However, the machine-readable Stat Registry should remain the authoritative
structured source for stat metadata. File DOX should link/summarize rather than
copy the entire registry.

## 6.4 Research query surfaces — useful at module boundaries

`research/` and the future `ResearchDB` facade can use file-level DOX for stable
public query contracts, return types, filters, rights behavior, and compatibility.

## 6.5 Migrations and generated SQL — usually directory-level only

Numbered migration SQL already has a strong local identity and should contain
its own SQL comments. Requiring a second sidecar for every migration would likely
be redundant.

The directory `AGENTS.md` plus table contracts/ADRs should normally be enough.

## 6.6 Tests — usually directory-level only

Tests are evidence for the contracts rather than the primary object being
explained. A `tests/AGENTS.md` should document isolation/fixture rules. Per-test
sidecars would add little value.

# 7. How DOX relates to normal documentation

DOX should not replace `README.md`, architecture docs, runbooks, or ADRs.

Use this separation:

| Artifact | Owns |
| --- | --- |
| `README.md` | human entry point and product/use overview |
| root `AGENTS.md` | global engineering contract + DOX router |
| child `AGENTS.md` | subtree contract + router |
| `file.ext.dox.md` | exact durable contract for a source file |
| architecture docs | deeper cross-cutting design/rationale |
| runbooks | operational procedures |
| ADRs | decision history and rationale |
| plans/specs | intended future/change work |
| code/docstrings | implementation-level API details |
| tests | executable evidence |
| generated catalogs | machine-derived reference truth |

A DOX file should link to deeper material rather than re-copy it.

# 8. Multi-agent behavior

The canonical project knowledge should remain vendor-neutral Markdown.

## Codex

Codex natively uses hierarchical `AGENTS.md` files. The local `AGENTS.md` then
instructs Codex to read matching file-level DOX before source edits.

No full `CODEX.md` duplicate is needed.

## Claude Code

Claude uses `CLAUDE.md` as its native project memory/instruction file. Keep it as
a thin adapter into the canonical DOX root, and use nested adapters or supported
path rules so local DOX routing is visible.

Once Claude sees the applicable DOX contract, the contract can direct it to the
specific source sidecar. The sidecars do not need native auto-loading support.

## Gemini CLI / Agy

Use a thin `GEMINI.md` bridge or configure Gemini's context filenames to include
`AGENTS.md`. The same DOX routing instructions then apply.

Bounded delegated Agy prompts should still state scope and safety explicitly;
DOX augments delegation rather than assuming every orchestrator propagates the
same context.

## Agent Zero

Agent Zero is a natural consumer of the complete protocol and demonstrates the
file-documented profile pattern in production.

# 9. Why this helps agents materially

## Faster orientation

Instead of asking an agent to rediscover a component from scratch, DOX gives it a
small local contract first.

## Better context efficiency

The entire project manual does not need to occupy the model's prompt. Context is
loaded by the path being edited.

## Better handoffs between models

Claude, Codex, Gemini, Agent Zero, and human contributors see the same durable
component contracts even when their chat histories and system prompts differ.

## Better maintenance discipline

The requirement to update sidecars/indexes in the same behavioral change makes
knowledge maintenance part of definition-of-done.

## Better refactoring

Ownership and dependency contracts can be moved with code during decomposition,
making hidden responsibilities visible.

## Better review

A reviewer can compare source behavior against the adjacent declared contract
without searching a giant ADR log first.

# 10. Risks and controls

## Documentation drift

Risk: sidecars become false documentation.

Controls:

- same-change update rule;
- structural CI coverage where directories require sidecars;
- targeted semantic review;
- sidecars point to executable tests;
- delete stale sidecars on rename/delete.

## File proliferation

Risk: DOX doubles the visible file count in large flat packages.

Controls:

- only local `AGENTS.md` may declare a directory file-documented;
- use full coverage where file independence/contracts justify it;
- split large domains into subdirectories instead of endlessly adding sidecars to
  one flat folder;
- do not sidecar generated/trivial files unless there is durable contract value.

## Generated low-value prose

Risk: an agent generates generic summaries that merely paraphrase code.

Control: DOX must record information that helps a future editor act safely:
contracts, ownership, invariants, side effects, dependencies, domain semantics,
and verification. Delete filler.

## Conflicting truth

Risk: code, Stat Registry, table contract, DOX, and docs all contain a formula or
schema description.

Control: name the authoritative source. DOX summarizes and links; it must not
become a competing structured registry.

# 11. Verification and tooling

Once the manual protocol is stable, add lightweight structural checks.

A future `scripts/check_dox.py` could verify:

- every indexed child `AGENTS.md` exists;
- each child is indexed by its nearest parent;
- every file in a declared file-documented directory has its required sidecar;
- no orphan sidecars remain after source deletion/rename;
- sidecars contain required section headings;
- referenced verification test paths exist;
- tool-specific bridge files remain small;
- links to local DOX files resolve.

Do not attempt to prove semantic correctness of prose with a brittle parser.
Structural checks plus human/agent review are enough initially.

# 12. Relationship to the Stat Registry and table contracts

DOX and the planned machine-readable registries complement each other.

For example, a future `stats/batting.py.dox.md` can say:

```text
Owns batting formula implementations used by research relations.
Authoritative stat definitions: stats registry.
Authoritative table grains: TABLE_CONTRACTS / generated relation catalog.
Relevant validation: tests/...
```

The registry contains structured values. DOX tells the editor what owns them, how
the module fits the architecture, and what must be checked when changing it.

Similarly a connector DOX should not copy every raw column. It should link to the
source/table catalog and explain acquisition semantics that are otherwise hard to
infer.

# 13. Cross-project standard

If the MLB rollout works, DOX is a strong candidate for a reusable convention
across the owner's repositories.

The reusable standard should include:

```text
AGENTS.md                       root contract/index
src-or-package/AGENTS.md        subsystem contract
... optional nested AGENTS.md
... optional file.ext.dox.md    only in declared file-documented profiles
CLAUDE.md                       thin bridge
GEMINI.md                       thin bridge
```

A generic project initializer could:

1. inventory repository boundaries;
2. build the initial Child DOX Index;
3. identify flat directories suited for file-documented profiles;
4. create concise contracts from actual code/tests;
5. run coverage validation;
6. leave uncertain semantics marked for human review rather than inventing facts.

The resulting DOX tree should be generated from the repository's real structure,
not copied verbatim from another project.

# 14. Recommendation for `mlb-baseball`

Adopt the protocol in stages, but treat file-level DOX as a real part of the
design rather than an optional curiosity.

Recommended sequence:

1. reconcile current instruction contradictions;
2. establish the canonical root DOX contract/index;
3. create the first directory contracts (`tests`, `docs`, `connectors`);
4. declare `connectors/` the first file-documented DOX profile and document its
   direct connector modules;
5. add transitional sidecars for `cli.py`, `conform.py`, and `mlb_api.py` as
   appropriate;
6. add structural DOX validation;
7. evaluate effect on Codex/Claude/Gemini/Agy work quality and context use;
8. extend to future `stats/` and `research/` packages;
9. migrate the same protocol into other repositories only after the MLB tree has
   survived normal development and refactoring.

## Bottom line

The important idea is not simply "put an `AGENTS.md` in several folders."

The important idea is:

> **Make the repository itself a recursively indexed, source-adjacent knowledge
> system that an agent can traverse just-in-time before editing code, and require
> that knowledge to evolve with the code.**

That is the DOX capability worth adopting.