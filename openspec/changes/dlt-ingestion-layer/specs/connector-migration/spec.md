# Spec Delta

## Purpose
Defines how an existing connector is moved onto the staged ingestion layer safely: one source at a time, with parity evidence before the switch, and the old path kept for rollback.

## ADDED Requirements

### Requirement: One source at a time
A connector SHALL be migrated in its own step, and no two sources SHALL be switched in the same step.

#### Scenario: Migration order
- **WHEN** the next source to migrate is chosen
- **THEN** exactly one source is switched and its result recorded before another starts

### Requirement: Parity is proven before the switch
A migrated connector SHALL produce, for the same input range, the same set of rows and key values as the old connector, and the comparison SHALL be recorded in the change's results.

#### Scenario: Parity check
- **WHEN** the old and the new path load the same range into separate scratch tables
- **THEN** their row counts, key sets and column values match, or each difference is listed and accepted by the owner

### Requirement: The old path stays available for rollback
The previous connector path SHALL remain runnable until the owner retires it, and returning to it SHALL need no data repair.

#### Scenario: Rolling back
- **WHEN** the new path is switched off after deployment
- **THEN** the old path runs on the next scheduled run and the loaded data is unchanged

### Requirement: Operator surface and contracts are unchanged
`mlb ingest <source>` modes, table and column names, the rights profile, health checks and coverage entries SHALL keep working as before, or be updated in the same change.

#### Scenario: Same command after migration
- **WHEN** an operator runs `mlb ingest <source> --mode update` after the source is migrated
- **THEN** it behaves as before and `mlb doctor` reports the source's checks as before

### Requirement: Retirement needs evidence and approval
The old path SHALL be removed only after at least 7 scheduled runs of the new path without a failure that the old path would not have had, and with the owner's approval.

#### Scenario: Retiring the old path
- **WHEN** the owner approves removal after 7 clean runs
- **THEN** the old code, its tests and its documentation are removed in one change
