# Operational Scripts DOX

## Purpose

Own shell/Python operational entry points for recurring updates, backfills,
bootstrap helpers, maintenance, validation, and administrator workflows.

## Ownership

Scripts orchestrate existing package/CLI capabilities. They should not become a
second implementation of ingestion, conformance, statistics, migrations, or
business formulas.

## Local Contracts

- Shell scripts should use a clear shebang and strict mode (`set -euo pipefail`)
  unless a documented reason requires different error semantics.
- Validate required executables, environment variables, paths, and permissions
  before starting destructive or long-running work.
- Make database targets explicit. A script that can mutate PostgreSQL must not
  make it easy to confuse production with a disposable test database.
- Prefer calling the supported `mlb` CLI/package functions over embedding new SQL
  or reimplementing connector logic in shell.
- Long-running/backfill scripts should log start/end, scope, important options,
  failures, and resume state sufficiently for postmortem/debugging.
- Use bounded concurrency and source-aware rate limiting; more workers are not
  automatically better for remote APIs or PostgreSQL.
- Destructive one-off operations should support a dry-run/preview or explicit
  confirmation when feasible.
- Recurring scripts should be idempotent/resumable whenever the underlying stage
  supports it.
- Never hardcode secrets, tokens, machine-specific home paths, or credentials.
- Do not silently swallow partial failures. Exit non-zero when the requested job
  did not complete successfully, while preserving enough state to retry safely.

## Work Guidance

Before creating a new script, confirm the workflow cannot be expressed cleanly by
an existing CLI subcommand, Make/CI target, or documented invocation. Favor fewer,
well-owned scripts over wrappers around wrappers.

When a script calls several pipeline stages, preserve their required order and do
not bypass locks/health/preflight checks for convenience.

Document recurring cron/systemd usage in the appropriate runbook rather than
embedding environment-specific scheduling details in comments alone.

## Verification

- Run `shellcheck`/the repository shell lint path for changed shell scripts when
  configured.
- Run syntax checks and the safest representative dry-run/test invocation.
- For scripts that invoke PostgreSQL behavior, use the isolated test database or
  a documented non-production rehearsal target.
- For source/API scripts, avoid making CI depend on live remote services.

## Child DOX Index

No child DOX files initially. Add a child if a durable script family develops a
separate operating contract (for example release tooling vs data backfills).
