@AGENTS.md

# CLAUDE.md — Claude Code operating rules

This file is the **Claude-specific overlay** for this repository. Shared project
truth, architecture, safety invariants, and filesystem routing live in the DOX
`AGENTS.md` hierarchy. This file intentionally keeps Claude-specific behavior that
may differ from Codex, Gemini/Agy, Agent Zero, or other harnesses.

Do not treat `@AGENTS.md` as meaning this file is redundant. Claude must apply
both:

1. the applicable shared DOX chain for the files being touched; and
2. the Claude-specific working rules below.

## Progressive context loading

Before editing any file:

1. read the root `AGENTS.md` imported above;
2. identify every path likely to be touched;
3. walk from repository root to each target and read every nested `AGENTS.md`;
4. if the nearest local contract declares a file-documented DOX profile, read the
   matching `<source>.dox.md` before editing the source;
5. read only the linked tests, ADRs, runbooks, references, or plans relevant to the
   task;
6. load/use a skill or long procedure only when the task actually needs it.

This is deliberate progressive disclosure. Do not preload the whole docs tree or
large historical plan/ADR logs merely to feel informed. Start local and expand
context when the local contract points to a dependency or uncertainty.

If a nested `CLAUDE.md` or path-scoped Claude rule is added later, apply it as an
additional Claude-specific layer for that subtree. It may specialize Claude's
workflow/tool behavior, but it must not silently contradict verified project facts
owned by the canonical DOX/source contracts.

## Database safety — Claude-specific execution rule

The production database is real. Never guess the database target of a destructive
command.

- `mlb` is the normal production database name in this project.
- Pytest does **not** work in one shared mutable `mlb_test` database anymore.
  `tests/conftest.py` uses `pytest-postgresql` to create a unique disposable
  database per pytest process, based on `TEST_DATABASE_URL`, and redirects
  `DATABASE_URL` to that disposable database for the suite.
- `mlb_test` may still be the base/default service database used to create those
  disposable databases (and is used directly by some DB-contract setup such as
  pgTAP in CI). Do not describe it as the one fixed pytest working database.
- `tests/conftest.py::_assert_test_database_url` is a critical guard against tests
  targeting a database whose name does not contain `test`. Do not weaken it
  casually.

Before running `DROP`, `TRUNCATE`, broad `DELETE`, `pg_restore`, `mlb restore`, a
migration, or another destructive command, make the target database explicit in
the command/output or tell the owner which target will be affected first. If the
target is not obvious at a glance, resolve that ambiguity before executing.

## Talking to the owner

Explain the bottom line in plain language first. Use technical detail where it
helps, but avoid dense jargon-first explanations. Prefer short, cohesive sections
over large walls of text.

When work is complex, keep the owner informed with concise progress updates and
surface important findings as soon as they are verified rather than saving every
finding for the end.

When a genuinely useful next improvement follows from evidence, mention it
briefly after completing the current task. Do not pad every response with generic
"next steps."

## Claude planning and scope discipline

- Follow the active product/plan state and the local DOX contracts. Do not pull a
  later modeling/site work package forward merely because it is interesting.
- Do not add a new data source until `docs/DATA_SOURCES.md`, rights/profile
  implications, and the connector ownership contract have been reviewed and
  updated as part of the same accepted change.
- Assume a zero-dollar recurring-data/service budget unless the owner explicitly
  changes that constraint.
- For cross-cutting infrastructure, check established libraries/patterns before
  designing a bespoke replacement.
- Preserve existing useful assets. A new framework, directory, registry, or helper
  must solve a current problem rather than create a parallel abstraction for a
  hypothetical future use.

### Observe before recommending

Separate **what Claude found** from **what Claude recommends**.

- Measure before proposing performance rewrites, vectorization, new database
  engines, GPU acceleration, concurrency increases, or broad index changes.
- A rewrite is the last option after smaller local fixes are shown insufficient.
- When citing a repository rule/ADR as a hard constraint, quote or link the actual
  current text rather than relying on remembered wording.
- If current code contradicts an old plan/doc, verify which is authoritative and
  repair the stale living document rather than forcing code to match stale prose.

## Delegation / subagent behavior

Claude may delegate bounded research, implementation, repetitive verification, or
review work when the available harness supports it and delegation reduces context
load or parallelizes independent tasks.

Every delegated task should state:

- exact goal and files/subtree;
- applicable plan and DOX chain;
- whether edits are allowed;
- production/test database safety;
- verification expected;
- what must be returned: changed files, commands/results, limitations/findings;
- that the delegate may not merge, delete worktrees/branches, rewrite unrelated
  user/parallel changes, mutate production data, or silently start the next work
  package.

Claude must inspect the returned diff/evidence itself. A delegate's "tests pass"
self-report is not sufficient proof.

If agent-specific skills/rules are introduced later, use them for repeatable
Claude procedures instead of copying long procedures into this always-loaded file.

## Testing behavior

The detailed shared testing contract lives in `tests/AGENTS.md`; follow it whenever
touching tests or code whose correctness depends on those fixtures.

Claude-specific reminders:

- Mock network I/O, not PostgreSQL behavior that depends on transactions, locks,
  COPY, DDL, partitioning, or constraints.
- A connector change needs production-shaped load/idempotency coverage, not only a
  parsing unit test.
- A failure involving connection/transaction state needs a real PostgreSQL
  regression.
- A CLI subcommand/option change needs a test through real argparse/CLI dispatch,
  not only the underlying handler.
- Statistical/formula changes need hand-calculated fixtures and an independent
  tie-out where a credible source exists.
- Never say the suite/linter passed unless Claude actually ran it in the current
  environment. If the current tool surface cannot execute tests, say so and use
  CI as the external verifier rather than inventing a local result.

## Modeling-specific Claude rules

Modeling is currently subordinate to the research-database product focus. When
model work is explicitly active, also read `mlb_baseball/model/AGENTS.md`,
`docs/RESEARCH.md`, and the applicable plan/ADR.

Claude may explore broad techniques—regularized models, ensembles, neural/
attention methods, hierarchical models, domain-engineered features—but must keep
the same scientific bar:

- chronological/rolling-origin validation, never random primary folds;
- transparent baselines first;
- strictly out-of-fold stacked training predictions;
- final forward/test data not used for feature/model selection;
- log loss, Brier score, calibration, sharpness/coverage and uncertainty rather
  than headline accuracy alone;
- suspiciously strong game-winner performance triggers a documented leakage
  investigation, not an automatic accusation or automatic promotion;
- promotion remains a recorded promote/hold/return-with-gaps review (ADR-274).

Do not let an LLM become the deterministic source of a stored gold statistic or
production probability. Agents may research, propose, review, explain and triage.

## Naming and code-quality reminders

Shared code architecture is owned by the nearest `AGENTS.md`/sidecar. Claude should
also preserve these established repository conventions:

- project-owned object names should normally be one or two words; source-faithful
  raw vocabulary is exempt where shortening would destroy a familiar source name;
- schema layers remain exactly `raw`, `core`, `gold`, and project metadata layers
  already accepted by architecture; do not invent bronze/silver aliases;
- no silent `except: pass`, dead commented-out implementations, or unfinished
  TODOs used as a substitute for completing accepted work;
- prefer explicit boring pipeline code to clever hidden behavior;
- read the module, its sidecar if present, callers, and nearby tests before
  creating another helper/pattern;
- use proper reusable interfaces when reuse is real now, but do not create an
  inheritance/plugin framework for hypothetical future sources.

## Health and operational visibility

When changing a connector or dependency that can become stale/unavailable,
consider its existing `health_check()` and `mlb doctor` coverage in the same
change. Reuse shared `Check` helpers rather than adding ad-hoc health-query styles.

A source returning partial failures, stale data, or changed schema must remain
visible in run tracking/health; successful process exit is not a substitute for
source correctness.

## GitHub and review workflow

- Work on focused branches/PRs. Protected `main` is not a direct-push target.
- Preserve unrelated user and parallel-agent changes.
- Commit messages explain why; PRs should be coherent reviewable slices rather
  than accidental checkpoints.
- Address human and automated review comments on PRs Claude is actively working
  with. Verify bot claims against actual code/library behavior before accepting or
  rejecting them.
- Fix real findings with appropriate tests/docs. If a suggestion is wrong or
  deliberately out of scope, explain concretely why rather than silently ignoring
  it.
- Bot infrastructure/service failures are not repository bugs; distinguish them
  from actual findings.
- Creating a focused branch, commit, issue, or PR is pre-authorized by existing
  repository policy. Force-pushing, closing issues, deleting branches, merging
  PRs, or rewriting someone else's work still needs explicit authorization.

## Claude closeout pass

Before Claude declares a task complete:

1. inspect the final diff, not only individual edits;
2. run the exact verification required by each affected DOX subtree where the
   current environment permits it;
3. perform the DOX pass: update local `AGENTS.md`/required sidecars/indexes when a
   durable contract changed;
4. confirm Claude-specific instructions/rules remain accurate if the task changed
   Claude workflow expectations;
5. check that living docs/registries reflect the shipped behavior and old plans
   are not being mistaken for proof;
6. report tests/checks actually run, anything not runnable, and any remaining
   limitations.
