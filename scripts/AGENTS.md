# Operational scripts DOX

## Purpose

This subtree owns repository maintenance and operational helper scripts. Scripts may automate repetitive developer/operator work, but they must remain explicit about prerequisites, targets, side effects, and failure behavior.

## Local Contracts

- Prefer existing package/library APIs over duplicating production logic in a one-off script.
- Shell scripts should use an appropriate shebang and strict mode (`set -euo pipefail`) unless there is a documented reason not to.
- Validate prerequisites and required environment/config before making changes.
- Database-changing scripts must make the target database obvious before any destructive operation. Never infer production/test safety from a vague environment name.
- pytest's current disposable DB mechanics are owned by `tests/conftest.py` / `tests/AGENTS.md`; scripts must not assume tests mutate the base `mlb_test` database.
- Destructive/one-time operations should support dry-run or an equally clear preview/confirmation mechanism when feasible.
- Idempotent/resumable behavior is preferred for maintenance/backfill operations.
- Emit useful logs/errors and non-zero exit status on failure. Do not silently continue past integrity failures.
- Do not embed secrets, API keys, passwords, or private local paths.
- Cross-platform behavior is welcome when cheap, but do not hide Linux/PostgreSQL requirements behind brittle abstractions.

## Work Guidance

- Keep scripts narrow; reusable logic belongs in the package with tests.
- When a script becomes part of a recurring supported workflow, promote its contract into a package API/runbook rather than letting undocumented shell behavior become infrastructure.
- Avoid adding wrappers that merely rename an existing `uv`, `pytest`, SQLMesh, migration, or CLI command without adding safety or orchestration value.

## Verification

- Lint/syntax-check the script.
- Exercise dry-run/no-op paths when present.
- For DB scripts, verify only against a disposable test database unless the owner explicitly requests a production operation.
- For scripts wrapping package code, run the package tests for that behavior as well.

## Child DOX Index

No child DOX currently. Add a child only if scripts split into durable domains such as release, database administration, or data-repair operations with materially different safety rules.
