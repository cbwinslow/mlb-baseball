## Purpose
Defines when the database counts as complete against its sources and how gaps are measured, repaired, explained and recorded.

## ADDED Requirements

### Requirement: Every raw table has an expectation or a written reason
`mlb coverage` SHALL report, for every table in `raw.*`, either an expected-versus-held comparison or a recorded reason no expectation can be derived.

#### Scenario: A table without an expectation
- **WHEN** the report is run and a raw table has no expectation
- **THEN** the table appears with its reason, and a test fails if a raw table is unregistered

### Requirement: Every gap is fixed or explained
Each gap SHALL end as repaired, or as an explained gap recorded durably (for example `unavailable` in the ingestion ledger, or an entry in `log.md` with its source evidence). A gap SHALL NOT be hidden by lowering an expectation without written evidence.

#### Scenario: A source never serves a game
- **WHEN** a repair finds the source has no data for an expected item
- **THEN** the item is recorded as unavailable at the source and the report counts it as accounted-for, not missing

### Requirement: Repairs are repeatable and reproduced by bootstrap
Every repair path SHALL be idempotent, and SHALL be reproducible by a bootstrap from an empty database.

#### Scenario: Running a repair twice
- **WHEN** a repair is run twice
- **THEN** row counts after the second run equal those after the first

### Requirement: Decisions and actions are logged
Each action that reads or writes production, and each decision with its reason, SHALL be appended to `openspec/changes/data-completeness/log.md` when it happens.

#### Scenario: A production repair
- **WHEN** a repair command is run against production
- **THEN** the log records the command, the approval, the before and after coverage numbers, and the outcome
