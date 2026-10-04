## Why

Scheduled jobs fail silently and are never retried (issue #274). On 2026-09-30 one process (pid 3414298) died during the 06:00 `update`; five sources were left "stale" and stayed behind until the next night, and nobody was told. `conform` failed three mornings in a row (2026-09-24..26) before it was noticed. The scheduling is plain cron plus a shell script, with no retry, no alert, and no quick way to see the last result of each job. This project is meant to be installed on other people's machines, so the fix must work without any extra service.

## What Changes

- **One Python nightly command** (`mlb nightly`) replaces the step logic in `scripts/mlb_daily_update.sh`. It runs each step as a child process, so a step that dies (crash, kill, out of memory) is seen by its parent and can be retried. The shell script shrinks to "cd to the repo, call `mlb nightly`".
- **Retry policy per step**, bounded and with a pause: network-bound steps (`update`) retry only the failed sources; code-bound steps (`migrate`, `conform`, `report`, `predict`) are not retried (a deterministic failure repeats and costs 40+ minutes each time) but are reported at once.
- **Alert hook**: one optional setting, `alert_command`, run with a plain-text message on failure. Default is none (log only), so a fresh install needs nothing. Documented examples: ntfy, a webhook, mail, an Uptime Kuma push URL.
- **`mlb runs`**: a fast view (one query on `meta.ingestion_run`) of each job's last result, age and duration, with `--check` that exits non-zero when a job is stale or last failed. Intended for a cron entry that calls the alert hook; `mlb status` stays as the slow exact-count view.
- **Run history for steps**: every nightly step is recorded in `meta.ingestion_run` (attempt number, outcome, duration) so speed and failures can be tracked over time.

## Capabilities

### New Capabilities
- `job-reliability`: bounded retries, failure alerts through a configurable hook, and a quick last-result view for scheduled jobs.

### Modified Capabilities

(none)

## Impact

- Code: new `mlb_baseball/nightly.py` (one module), `mlb_baseball/cli.py` (`nightly`, `runs`), `mlb_baseball/config.py` (`alert_command`), `scripts/mlb_daily_update.sh` (reduced), `mlb_baseball/ingest.py` (attempt recorded).
- Database: `meta.ingestion_run` gains an `attempt` column and a `mode` value for nightly steps (numbered migration; the existing check constraint on `mode` must be extended).
- Docs: one section in the user manual on alerts; no new standalone docs.
- Out of scope: replacing cron, a database job queue, pg_cron (Python steps need network and the repo's environment).
