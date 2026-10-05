## Purpose

Defines what each ingestion run and item records so duration, throughput, progress and failures can be read from the database.

## ADDED Requirements

### Requirement: Runs record timing and throughput
Each ingestion run SHALL record start, finish, items planned, items done, rows loaded and requests made, and SHALL update progress while running at a bounded rate (at most once a minute).

#### Scenario: Running job
- **WHEN** a backfill is running
- **THEN** its run row shows items done, items planned and last progress time

### Requirement: Items record attempts and durations
Each ledger item SHALL record attempts, the duration of its last attempt, and the last error, and keep failed attempts visible rather than overwriting them with a later success without trace.

#### Scenario: Retry then success
- **WHEN** an item fails once and later loads
- **THEN** its attempt count is 2 and the first error is still recorded

### Requirement: Stuck and slow runs are detected
`mlb doctor` SHALL fail a check when a run shows no progress for longer than its allowed gap, or its throughput is below a recorded floor for its source, and the message SHALL name the run and its last progress.

#### Scenario: Silent run
- **WHEN** a run has made no progress for the allowed gap
- **THEN** the doctor reports the run id, source and time of last progress

### Requirement: Database-side timing uses installed tools first
Query-level timing SHALL use `pg_stat_statements` (installed); any further extension (`pg_profile`, `pg_wait_sampling`) SHALL be adopted only after a measured question the existing tools cannot answer.

#### Scenario: Proposing a new extension
- **WHEN** a new extension is proposed
- **THEN** the proposal cites the question it answers and the measurement showing existing tools fall short
