## Purpose

Define what a healthy nightly pipeline means for the production `mlb` database: failures leave no stale state, health checks report only real problems, a recoverable backup exists, every phase is timed, and a fast incremental run gives the same data as a full rebuild.

## ADDED Requirements

### Requirement: A failed or interrupted run leaves no stale state

After any pipeline run ends, whether it succeeded, failed or was killed, no `meta.ingestion_run` row SHALL remain in `running` state without a live process, and no workflow lock SHALL remain held by a dead process. The next run SHALL be able to start without manual database edits. Repair SHALL decide a run is dead from the process list and the database's own lock and session state together, and SHALL never mark a live run failed.

#### Scenario: A run is killed partway through

- **WHEN** a run is killed while some sources are still loading
- **THEN** `mlb repair-runs` marks those runs failed, no advisory lock remains held by a dead session, and the following run starts normally

#### Scenario: A run is genuinely still running

- **WHEN** a process holding the lock is alive
- **THEN** no repair step marks its runs failed or releases its lock

### Requirement: Health checks test only what the system is meant to contain

`mlb doctor` SHALL fail a check only when the condition it tests is a defect of the system as designed. A table that exists only after an owner-triggered backfill SHALL be reported as "not backfilled" and SHALL NOT count as a failure. Every failure SHALL name what is wrong and the command or decision that resolves it.

#### Scenario: Optional backfill tables are absent

- **WHEN** `raw.polymarket_price` and `raw.kalshi_candle` do not exist because the backfill was never triggered
- **THEN** `mlb doctor` reports them as informational and the pass/fail count excludes them

#### Scenario: A real defect

- **WHEN** model output values lie outside their documented valid range
- **THEN** `mlb doctor` fails that check and states the count and the owning module

### Requirement: Every doctor failure is classified

Each failure reported by `mlb doctor` on production SHALL be recorded as one of: real defect (with a tracked fix), wrong check (corrected), or accepted (with written reason, review date and the owner's sign-off, supported by a sample of the affected rows). No failure SHALL remain unclassified when the change is closed.

#### Scenario: Close-out

- **WHEN** this change is archived
- **THEN** a results document lists every doctor failure observed at start with its classification and evidence

### Requirement: A backup exists before any structural change

Before any migration or rebuild that alters production `core` or `gold`, a backup of production `mlb` SHALL have been taken and verified restorable to an explicitly named disposable database that is never the production database, with row counts, indexes and constraints compared on every schema, and `mlb doctor` SHALL show its age.

#### Scenario: Backup is missing

- **WHEN** no backup is recorded
- **THEN** the structural change does not start and `mlb doctor` reports the backup as missing

### Requirement: Every phase is timed

Each nightly run SHALL record the elapsed time of update (per source), conform (per step), report (per relation) and predict (per step), queryable from the database without reading log files.

#### Scenario: Reading last night's timings

- **WHEN** an operator queries the run history after a nightly run
- **THEN** the elapsed time of every phase and step, including each source's update, each conform step, each report relation and each predict step, is available, for scheduled runs as well as `mlb nightly`

### Requirement: Incremental and full rebuilds give the same data

When `mlb conform` runs incrementally, the resulting `core` and `gold` content (both layers) SHALL equal the content of a full rebuild from the same raw data, compared on all non-key values and with internal ids and build timestamps ignored. Internal id stability SHALL be verified separately.

#### Scenario: Equivalence on a fixture

- **WHEN** a fixture database is built in two incremental steps and once in full
- **THEN** every row's non-key values match between the two results, and no value differs even where the natural keys match

#### Scenario: A corrected old value

- **WHEN** a raw value inside a past season changes without changing its row count or key
- **THEN** the next incremental run rebuilds that season and the result matches a full rebuild

### Requirement: Maintenance operations fail fast

Maintenance statements that take strong locks (truncate, partition attach or detach, migrations, backups) SHALL run with a lock timeout and SHALL fail rather than queue behind readers.

#### Scenario: A reader holds a conflicting lock

- **WHEN** a maintenance statement cannot obtain its lock within the timeout
- **THEN** it fails with a clear message, retries or stops, and does not block other sessions behind it

### Requirement: Raw data is never changed to make a check pass

No recovery, rebuild or check-fixing step SHALL insert, update or delete rows in `raw` tables. Any difference found in raw data SHALL be recorded as an issue.

#### Scenario: A check disagrees with raw data

- **WHEN** a check fails because of raw content
- **THEN** the change records the difference and leaves raw unchanged
