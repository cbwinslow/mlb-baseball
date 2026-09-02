# Execution plans DOX

> **Status: retired.** The `plans/` workflow is replaced by OpenSpec (`openspec/changes/` + the `NOW / NEXT / LATER` block in `openspec/project.md`). Files here are historical.


## Purpose

This subtree owns long-horizon and staged execution plans. Plans describe intended work and acceptance gates; they do not automatically override newer verified repository state or current product direction.

## Local Contracts

- Treat `plans/README.md` as the navigation/status entry point for this subtree.
- Distinguish active/current plans from paused, completed, superseded, or historical plans.
- A plan should describe scope, non-goals, dependencies, ordered work packages, verification, and acceptance gates.
- Plans should reference canonical architecture/source/stat/rights docs instead of duplicating their full contents.
- When implementation reveals that a plan assumption is wrong, update the plan/status rather than forcing code to fit stale prose.
- Do not use plans as running diaries. Durable decisions belong in ADRs/current docs; detailed session notes belong elsewhere or can remain in PR history.
- Delegated-agent work packages must be bounded and must not implicitly authorize merging, destructive DB work, or expansion into later plan phases.
- Current project focus takes precedence over an older numbered sequence when `plans/README.md`, `docs/MAP.md`, or a newer owner-approved plan explicitly says so.

## Progressive Disclosure

Root/project context should point agents to the current plan rather than embedding the entire plan in `AGENTS.md`/`CLAUDE.md`. Load the plan only for tasks governed by it.

## Verification

Before marking a plan phase complete:

- inspect the actual diff/source state;
- run the phase's named tests/quality gates;
- check linked docs/DOX for drift;
- record known limitations rather than silently carrying them forward.

## Child DOX Index

No child DOX. Individual plan files are already bounded context artifacts and normally do not need adjacent sidecars.
