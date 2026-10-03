## Purpose

Make scheduled jobs recover from transient failure, tell the owner when they do not recover, and show at a glance what last ran.

## ADDED Requirements

### Requirement: Network-bound steps are retried, failed sources only

`mlb nightly` SHALL retry a failed `update` step a bounded number of times with a pause between attempts, and each retry SHALL run only the sources that failed. A step that is killed or crashes SHALL count as a failed attempt.

#### Scenario: A source fails once, then succeeds

- **WHEN** one source fails on the first attempt and succeeds on the second
- **THEN** only that source runs again, the step is reported successful, and both attempts are recorded in `meta.ingestion_run`

#### Scenario: The process dies mid-step

- **WHEN** the `update` child process is killed after some sources finished
- **THEN** the parent records the attempt as failed and retries the sources without a recorded success for this night

#### Scenario: Retries are exhausted

- **WHEN** a source still fails after the last allowed attempt
- **THEN** the step is reported failed with the number of attempts and the last error, and the alert hook is called once

### Requirement: Code-bound steps are not retried

`migrate`, `conform`, `report` and `predict` SHALL NOT be retried automatically. A failure SHALL be reported at once and SHALL skip the steps that depend on it, as the current script does.

#### Scenario: conform fails

- **WHEN** `conform` exits non-zero
- **THEN** `report` is skipped, `predict` still runs, and the alert hook is called once with the failing step and its last log lines

### Requirement: Failures are alerted through one optional hook

The system SHALL call the configured `alert_command` with a plain-text message when a nightly step ends failed or when `mlb runs --check` finds a stale or failed job. With no `alert_command` set it SHALL only log. A failing hook SHALL NOT change the outcome of the job it reports on.

#### Scenario: No hook configured

- **WHEN** a step fails and `alert_command` is unset
- **THEN** the failure is logged and the run exits non-zero, and nothing else is called

#### Scenario: The hook itself fails

- **WHEN** `alert_command` exits non-zero
- **THEN** the failure of the hook is logged and the nightly exit code is unchanged

### Requirement: A quick last-result view

`mlb runs` SHALL print, for every job recorded in `meta.ingestion_run`, its last result, how long ago it finished and its duration, using one query and no table counts. `mlb runs --check` SHALL exit non-zero when any job's last run failed or no success is newer than that job's freshness threshold.

#### Scenario: Everything is healthy

- **WHEN** every job's last run succeeded within its threshold
- **THEN** `mlb runs --check` exits zero

#### Scenario: A job went stale

- **WHEN** no success exists for a job inside its threshold
- **THEN** the job is listed as stale and `mlb runs --check` exits non-zero

### Requirement: Query statistics are kept across nights

`mlb nightly` SHALL, after its steps, copy `pg_stat_statements` into `meta.query_stat_snapshot` (cumulative counters, 180 days kept) so slow-statement history survives the extension's small window and restarts. A failure to snapshot SHALL be logged and SHALL NOT change the nightly exit code.

#### Scenario: Extension unavailable

- **WHEN** `pg_stat_statements` does not exist in the database
- **THEN** the snapshot is skipped with a log line and the nightly result is unchanged
