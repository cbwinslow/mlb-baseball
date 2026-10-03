## Context

Observed (issue #274, `meta.ingestion_run`, `logs/mlb_daily_update.log`):

- `scripts/mlb_daily_update.sh` runs `migrate`, `update --skip mlb_api`, `conform`, `report`, `predict`, `doctor --populated`; each step is logged with duration and exit code, and a failure sets the overall exit code but nothing retries or alerts. It already calls `mlb repair-runs` first to clear runs whose process died.
- 2026-09-30: one process died during `update`; five sources were reaped as stale ("process no longer running"). That was process death, not a connector exception, so retry logic inside the process could not have helped: a parent must notice.
- `mlb_api` runs every 5 minutes (800 runs in 3 days, 1 failure, a 503 from the MLB server); the next tick is the natural retry.
- Per-connector failure isolation already exists in `_run_all` / `_run_group`; there is no retry.
- `meta.ingestion_run` has source, mode, status, rows, error, started/finished, pid, with check constraints on `mode` and `status`. `health.py` already has freshness thresholds (`DAILY_FRESHNESS_THRESHOLD_MINUTES = 28 * 60`).
- The owner's machine has an Uptime Kuma push script, but another user will not; the alert path must be configurable and optional.

## Goals / Non-Goals

**Goals:**
- A transient failure or a killed process is retried without human action.
- A non-recovering failure produces one alert through a channel the user chooses.
- One quick command shows what last ran.
- Works on a fresh install with no extra service.

**Non-Goals:**
- A job queue table, pg_cron, or any scheduler beyond cron (rejected: Python steps need the repo environment and network; more to maintain than the problem justifies).
- Changing what the steps do (see `stable-ids-incremental-conform`).
- A notification service integration list; one generic hook only.

## Decisions

**D1: A parent process supervises the steps (`mlb nightly`).** Steps run as child processes (`subprocess`), so the parent sees a non-zero exit, a signal or an out-of-memory kill the same way. Rejected: retry loops inside each step (cannot see its own death); keeping retries in bash (hard to test, grows).

**D2: Retry only what is transient.** `update` is network-bound and per-source, so retry the failed sources (default 3 attempts, pauses 1 min then 5 min, configurable). Code-bound steps are not retried: a deterministic failure repeats, and `conform` alone costs ~44 min per try. `mlb_api` is not part of `nightly` and keeps its 5-minute cadence; stale detection covers it (D4).

**D3: Alerts via one setting, `alert_command`.** The command is run with the message on stdin and as `$1`; no default; a failing hook is logged and ignored. This is how pros keep alerting portable (a webhook, `ntfy`, `mail`, a Kuma push URL are one-liners in the user's config). Rejected: built-in Slack/email clients (dependencies, credentials in the project).

**D4: `mlb runs` is one SQL query over `meta.ingestion_run`; `--check` compares the latest success to a per-source threshold** (daily sources 28 h as in `health.py`; `mlb_api` 15 min). A user cron entry running `mlb runs --check` and calling the hook on failure covers jobs that stop running entirely, which an in-job alert cannot.

**D5: Record attempts.** `meta.ingestion_run` gains `attempt` (default 1) and the `mode` constraint admits `nightly`; one row per step attempt gives duration trends without a new table. Alternative (a separate steps table) rejected: same data, one more table.

**D6: Keep the shell script as a thin shim.** It keeps `flock` and the log path (cron-friendly), then `exec`s `mlb nightly`. The existing `mlb repair-runs` call and the `--skip mlb_api` choice move into `mlb nightly`.

## Risks / Trade-offs

- A retry masks a flaky source → every attempt is recorded and shown in `mlb runs`, and a source that needed retries on several nights is visible.
- Retried sources are idempotent only if connectors are → they already replace by scope or append with keys; the retry scenario test uses a real PostgreSQL fixture to prove no duplicate rows.
- The alert hook runs arbitrary user-configured commands → it is the user's own config, invoked without a shell where possible (argument list), documented as such.
- Moving orchestration from bash to Python changes the nightly entry point → the shim keeps the cron line unchanged, and the old script's step order and gates are covered by tests before removal.

## Migration Plan

1. Migration for `attempt` and the `mode` constraint.
2. Land `mlb runs` first (read-only, immediately useful).
3. Land `mlb nightly` and the shim; run it manually once next to the old script's output, then switch the cron line only if unchanged (it is: the shim keeps its path).
4. Remove the old step logic from the shell script.
Rollback: restore the previous script; the new columns are unused by it.

## Open Questions

- Default `alert_command` examples to document first (ntfy and a generic webhook are the likely two).
