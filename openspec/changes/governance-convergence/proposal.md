## Why

The project has accumulated strong architecture decisions, contracts, runbooks,
OpenSpec changes, and operational checks, but the recent holistic review found
that several durable rules are duplicated, scattered, or stale. The clearest
example is the feature-layer boundary: the constitution and
`docs/FEATURE_STORE.md` make DuckDB `feat.*` canonical for point-in-time
model features, while older table-contract wording still describes `gold` as
owning point-in-time feature families. The review also produced important
North Stars, completion gates, and repair priorities that must become durable
project state rather than remain only in a chat transcript.

We need one bounded governance-convergence change that folds those findings into
the documents that already own them, assigns every remaining finding to an
existing or named future change, and makes completion criteria machine-verifiable
where practical. This is consolidation, not a new parallel governance system.

## What Changes

- Add one concise project North Star and a set of durable engineering invariants
  to `openspec/project.md`, with detailed rules delegated to their existing
  owning contracts.
- Define document/decision precedence and the rule that verified code/data
  evidence triggers reconciliation of stale documentation rather than silent
  divergence.
- Establish **Platform Convergence** as an architecture-readiness gate before
  broad new Engine/model/product expansion.
- Reconcile the `raw` / `core` / `gold` / DuckDB `feat.*` descriptions
  across the constitution, architecture, and table contracts.
- Add subsystem North Stars and explicit single-writer, PIT, research-lineage,
  and contract-impact completion rules to existing owning documents rather than
  creating duplicate manuals.
- Map every high-priority finding from the 2026-10-05 holistic review to an
  existing active change, a durable contract, an automated gate, or a named
  future OpenSpec change.
- Keep GitHub issues as discoverability/status surfaces while OpenSpec remains
  the authoritative implementation specification and task list.

## Capabilities

### New Capabilities

- `project-governance`: one authoritative hierarchy from mission and durable
  invariants through subsystem contracts, OpenSpec work, machine gates, and
  recorded evidence.

No existing capability is semantically redefined by this change. The
feature-store documentation is reconciled to the already-adopted
`feature-store-boundary` contract rather than creating another delta for the
same rule.

## Impact

- Documentation/governance only in this change; no schema, ingestion, conform,
  model, market, or production-data mutation.
- Updates existing governing documents and the current convergence runbook.
- Creates no second constitution, roadmap, or duplicate task system.
- Follow-up implementation remains in the existing active changes wherever they
  already own the work.
