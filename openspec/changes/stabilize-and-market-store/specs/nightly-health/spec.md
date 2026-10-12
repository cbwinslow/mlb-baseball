# Spec Delta

## Purpose
Defines what the nightly pipeline must do when a step fails or stops, and keeps pipeline failures separate from data-health warnings, so that a red result always means something needs action.

## ADDED Requirements

### Requirement: Every failure raises an alert
A failed or timed-out nightly step SHALL send a notification through a configured alert channel, not only write a log line.

#### Scenario: A step fails
- **WHEN** a nightly step exits with a failure code
- **THEN** an alert naming the step and the last output is delivered to the configured channel

#### Scenario: No alert channel configured
- **WHEN** the nightly run starts and no alert channel is configured
- **THEN** the run reports that fact in `mlb doctor` instead of failing silently

### Requirement: The supervisor is watched from outside
The system SHALL send an external "finished" signal at the end of each nightly run, and an alert SHALL be raised when the signal is missing past the expected window.

#### Scenario: The supervisor process dies partway
- **WHEN** the nightly process is killed before it writes its finished line
- **THEN** the missing signal produces an alert within the expected window

### Requirement: Pipeline failures and data-health warnings are separate
The nightly exit code SHALL reflect only pipeline step failures. Data-health findings SHALL be reported in a separate daily digest and SHALL NOT change the exit code.

#### Scenario: Coverage finds a gap but all steps ran
- **WHEN** every step completes and the coverage check reports a data gap
- **THEN** the nightly exit code is success and the gap appears in the digest

### Requirement: Health checks do not scan the big tables
Full-count coverage and repair checks SHALL run weekly and SHALL read table statistics or the ingestion ledger instead of counting every row.

#### Scenario: Nightly coverage run
- **WHEN** the nightly coverage check runs
- **THEN** it completes without a full-table count on any market table

### Requirement: Loaders skip unchanged content
A loader SHALL skip a load, and write nothing, when the source content hash or Last-Modified value matches the last successful load.

#### Scenario: Second run with unchanged source
- **WHEN** a loader runs twice in a row against unchanged source content
- **THEN** the second run writes no rows and records the skip in `meta.ingestion_item`
