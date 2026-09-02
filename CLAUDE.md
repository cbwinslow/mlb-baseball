@AGENTS.md

# Claude Code — repository operating rules

> **START HERE: [`openspec/project.md`](openspec/project.md)** — the project constitution. **Workflow is OpenSpec** (`/opsx:propose` → `/opsx:apply` → `/opsx:archive`); the `plans/` workflow (now `docs/archive/plans/`) and conductor `/spec` are retired.

`AGENTS.md` is the shared project contract and filesystem DOX map. This file adds
**Claude-specific** working behavior. It is intentionally not a duplicate of all
project architecture, connector, test, SQL, or modeling rules.

When Claude enters a subtree that has its own `CLAUDE.md`, read that local file in
addition to the applicable `AGENTS.md` chain. If the target has a
`<filename>.dox.md` sidecar, read it before editing the source.

## Communicating with the owner

- Give the bottom line first, in plain language.
- Prefer short, concrete sentences over dense jargon. Add the technical term only
  when it helps.
- Clearly separate **what I found** from **what I recommend** when analysis and
  recommendation are both involved.
- If citing a repository rule as a constraint, quote or point to the exact owning
  file rather than presenting a remembered paraphrase as a hard rule.
- After finishing work, mention a next step only when evidence shows it is useful;
  do not pad every response with generic suggestions.

## Progressive context discipline

Claude should minimize irrelevant persistent context, not project knowledge.

For a target path:

1. Read root `AGENTS.md` and this file.
2. Walk into the target directory and load its local `AGENTS.md` and, when
   present, local `CLAUDE.md`.
3. Read a matching `*.dox.md` sidecar only for the implementation being changed.
4. Follow links to exact tests/ADRs/source/table/stat docs only as needed.
5. Load a skill/runbook only when performing that procedure.

Do **not** preload every connector/model sidecar or every long plan "just in
case." The point of the DOX layout is just-in-time context.

When a local shared rule belongs in `AGENTS.md`, do not copy it into `CLAUDE.md`
merely so Claude sees it. Import/read the local shared contract and reserve
`CLAUDE.md` for Claude-specific behavior.

## Scope and planning discipline

- Follow the current owner-approved focus in `openspec/project.md` (current
  phase + `NOW / NEXT / LATER`); do not pull paused/later model or website
  work forward because an older archived plan contains it.
- Before changing code, read the target module/class and near neighbors. Reuse
  existing project assets before creating another implementation.
- Keep a change bounded. Do not turn a requested fix into an adjacent rewrite,
  architecture migration, new source, or new framework without evidence and
  authorization.
- If repository state disproves an instruction/doc assumption, treat the code/test
  evidence as an observation and repair the stale owning documentation in the
  same change when practical.

## Established solutions first

Before proposing a bespoke solution to a cross-cutting infrastructure problem
(test isolation, HTTP retry, auth, migrations, CI orchestration, serialization,
client SDKs, etc.):

1. check whether an established maintained library/pattern already solves it;
2. compare it against the project's actual requirements/current implementation;
3. state the concrete reason if a custom implementation is still preferable.

Do not replace working project-specific code merely because a library is newer or
more fashionable.

## Evidence before rewrites or optimization

Do not propose a rewrite, vectorization, GPU/JIT path, concurrency change, or
"this is slow" conclusion from appearance alone.

- Measure representative runtime/query plans/memory/profile data first where the
  claim is performance-based.
- Prefer cheap local fixes before architectural replacement.
- Preserve stable facades while decomposing large modules such as `cli.py` and
  `conform.py`.
- Historical warnings in a local DOX sidecar are scoped evidence. Do not turn one
  connector's concurrency failure into a universal "never use threads" rule.

## Delegation and subagents

Claude may delegate bounded reconnaissance, repetitive implementation, test
construction, library comparison, or review when that improves quality/throughput.

A delegated prompt must be self-contained and include:

- exact target path/work package;
- the applicable local DOX/plan to read;
- what edits are allowed and what is out of scope;
- database/source-rights/PIT safety constraints relevant to the task;
- exact verification expected;
- a handoff listing changed files, tests run, findings, and limitations.

Delegated agents must not merge PRs, force-push, delete branches/worktrees, alter
production data, add paid services/sources, or expand into the next plan phase
without explicit authorization.

After delegation, Claude must inspect the resulting diff and re-run the relevant
checks before treating the work as complete. A subagent's self-report is not
proof.

## Database and test safety

Shared test mechanics live in `tests/AGENTS.md` / `tests/conftest.py`; read them
when touching tests. In particular, do not resurrect the old assumption that
pytest mutates one shared literal `mlb_test` database.

For any destructive manual database operation:

- make the target database explicit before execution;
- never infer safety from a vague environment name;
- production `mlb` is real data;
- use the repository's run-specific disposable PostgreSQL fixtures for tests.

Do not mock PostgreSQL transaction/lock/COPY semantics when the regression depends
on those semantics.

## Source and connector work

Detailed connector rules live under `mlb_baseball/connectors/`. For Claude:

- verify source/coverage/schema facts rather than guessing them;
- use bounded external/source checks only when needed to resolve a material fact;
- preserve source-faithful raw quirks;
- require parity evidence before replacing a mature connector/client;
- do not add a new data source or paid dependency without owner approval and
  source-rights documentation.

## Research/model work

Detailed model/PIT rules live in `mlb_baseball/model/AGENTS.md` and its Claude
context.

Claude should distinguish brainstorming/research from implementation. Broad model
or feature ideas are welcome as proposals, but they become project results only
after the repository's chronological/PIT/baseline/calibration evidence exists.

Promotion is a recorded review, not an automatic numeric gate. If a result is
implausibly strong, perform and document a leakage/PIT review rather than either
celebrating it or declaring leakage from one metric alone.

## Code quality behavior

- Prefer explicit, boring, maintainable code over cleverness in ingestion/data
  infrastructure.
- No silent `except: pass`, dead commented-out blocks, or TODOs standing in for
  required work.
- Reuse existing helpers and keep dependency direction clean.
- Build abstractions for demonstrated current reuse, not hypothetical future
  plugins.
- When a real reusable boundary exists, use clear typed/composable interfaces;
  do not confuse "avoid speculative abstraction" with "avoid structure."

## Review and GitHub behavior

- Preserve parallel/user changes.
- Work through focused branches and PRs.
- Address substantive human and automated review findings on PRs Claude is
  working on. Verify findings rather than blindly accepting/rejecting them.
- Explain why a finding is false/out of scope when declining it.
- Do not merge, close, force-push, or delete branches without explicit owner
  authorization.

## Definition of done for Claude

Before telling the owner a coding task is done:

- inspect the final diff;
- run the relevant tests and configured lint/type/SQL checks that are possible in
  the current environment;
- verify the owning DOX/docs/health/registry contracts were updated if behavior
  changed;
- report exactly what ran and what could not be run;
- do not convert a delegated agent's passing claim into your own unverified
  statement.

For documentation-only changes, source-review/link/structure verification may be
the relevant gate; do not pretend an unrelated full test suite was run.
