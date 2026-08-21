# Plan 00 — Workspace reconciliation and baseline

## Objective

Produce one understood, testable baseline before architecture work. Nothing in
dirty main or the Claude worktrees may be merged merely because it exists.

## Inputs requiring disposition

- Main: project review, game linkage/log5 corrections, evaluation/provenance WIP.
- Claude totals worktree: proposed `0029_gold_total_prediction.sql`.
- Claude reporting worktree: conflicting `0029_gold_reporting.sql` (rename to
  `0030` before any integration).
- Claude stacking worktree: stacking model without a migration.
- SQLMesh spike branch/worktree at commit `20a2dc4`.

## Work packages

### 00A — Inventory and provenance

Record branch, base SHA, dirty files, intent, ownership, tests, database effects,
and overlap for every worktree. Snapshot migration names and applied production
migrations. Do not edit or merge.

### 00B — Independent review

Review each change for leakage, game/prediction grain, source rights, schema
compatibility, idempotency, and tests. Classify `accept`, `revise`, `defer`, or
`discard`. In particular, stacked models must use out-of-fold base predictions;
otherwise defer them.

### 00C — Controlled integration

Integrate accepted units one at a time in dependency order: correctness fixes,
evaluation, provenance, reporting, totals, then stacking only if valid. Resolve
migration numbering before applying anything. Run focused tests after each unit
and the full suite at the end. Do not combine commits until each is independently
reviewable.

## Acceptance gate

- Main has no unexplained changes and no duplicate migration versions.
- Every retained change has a decision record and passing tests.
- `git diff --check`, Ruff, all unit tests, and relevant isolated-Postgres tests
  pass; production is read-only during verification.
- A baseline report lists exact commit(s), unresolved risks, and deferred work.

