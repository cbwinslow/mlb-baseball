## Purpose

Defines what the scheduled pipeline guarantees about derived research tables:
they are populated and current after every run, and any step that cannot do
that fails visibly.

## ADDED Requirements

### Requirement: A scheduled run applies pending schema changes before it rebuilds

The scheduled pipeline SHALL apply all pending migrations before it runs any
step that depends on the current schema. A migration failure SHALL stop the
dependent steps and be reported.

#### Scenario: A migration fails

- **WHEN** a pending migration fails
- **THEN** `conform`, `report` and `predict` do not run in that scheduled run
- **AND** the run exits non-zero and names the failed migration

#### Scenario: A new table is required by conform

- **WHEN** the code on disk requires a table that migrations have not yet created
- **THEN** the scheduled run creates it before `conform` starts
- **AND** `conform` does not crash for a missing relation

### Requirement: Every table a step empties is refilled in the same scheduled run

Any scheduled step that empties a derived table SHALL be followed, in the same
run, by the step that refills it. The scheduled run SHALL end by checking that
each game-level backbone relation and its roll-ups is non-empty, and SHALL exit
non-zero and name the empty relations when any is empty.

#### Scenario: A daily run completes

- **WHEN** the scheduled run finishes `conform`
- **THEN** `report` runs before the run ends
- **AND** the backbone relations have rows

#### Scenario: A rebuild step fails

- **WHEN** `report` fails after `conform` emptied the backbone
- **THEN** the run exits non-zero and names the empty relations
- **AND** the failure is visible in the run log and `mlb doctor`

### Requirement: The feature build refuses an empty source

The feature-store build SHALL fail with a message naming the empty source
relation when a source it reads is empty. It SHALL NOT produce a feature
relation with zero rows from an empty source without failing.

#### Scenario: A source relation is empty

- **WHEN** `core.game`, `gold.batting_game` or `gold.pitching_game` has zero rows and the feature build runs
- **THEN** the build fails naming the empty relation
- **AND** no zero-row feature relation is reported as a success

### Requirement: Step durations are recorded

Each scheduled step SHALL record its start, end and duration in the run log so
slow steps can be identified from evidence.

#### Scenario: A daily run finishes

- **WHEN** the scheduled run completes
- **THEN** the log has a start, end and duration for `update`, `conform`, `report` and `predict`

### Requirement: An incremental rebuild is identical to a full rebuild

If incremental rebuilds are adopted, an incremental catch-up over unchanged
frozen history SHALL produce exactly the rows a full rebuild produces, with
stable game ids for frozen seasons (including games identified only by
`game_pk`), and a full rebuild SHALL remain available.

#### Scenario: Incremental equals full

- **WHEN** a full rebuild and an incremental catch-up run over the same source data
- **THEN** every affected relation has identical rows and identical game ids for frozen seasons
