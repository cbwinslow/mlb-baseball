# Spec Delta

## Purpose
Defines what the pitch and play tables in `core` must carry from their raw sources, so any model or researcher can use `core` without re-reading `raw`.

## ADDED Requirements

### Requirement: Pitch table carries every measured Statcast field
`core.pitch` SHALL carry every `raw.statcast_pitch` column that holds a measurement or identifier, with numeric measurements stored as numbers, dates as dates, and blank source values stored as `NULL`.

#### Scenario: Measured column is present
- **WHEN** a pitch row has a plate location, movement, spin axis, release point, base state, fielder, handedness or run-expectancy delta in `raw.statcast_pitch`
- **THEN** the same value appears in the matching `core.pitch` row in a typed column

#### Scenario: Blank is not zero
- **WHEN** a raw value is blank
- **THEN** the `core` value is `NULL`, never `0`

#### Scenario: Excluded columns are documented
- **WHEN** a raw column is not carried
- **THEN** the table contract names it with a written reason (load metadata, or a column the source marks deprecated)

### Requirement: Play table carries the full Retrosheet event and MLB play fields
`core.play`, together with its Retrosheet detail table, SHALL carry every `raw.retrosheet_event` column except load metadata, and the MLB play-by-play fields not already in `core.play`, without changing the existing 19 `core.play` columns.

#### Scenario: Retrosheet detail joins one-to-one
- **WHEN** a Retrosheet play exists in `core.play`
- **THEN** exactly one detail row exists for it, and none exists for MLB-sourced plays

#### Scenario: Existing consumers unchanged
- **WHEN** a query uses only the original `core.play` columns
- **THEN** it returns the same rows and values as before the change

### Requirement: Rows link back to their raw source
Every widened `core` row SHALL keep the source keys needed to find its raw row.

#### Scenario: Pitch to raw
- **WHEN** a `core.pitch` row is read
- **THEN** its game key, at-bat number and pitch number identify exactly one `raw.statcast_pitch` row

#### Scenario: Retrosheet play to raw
- **WHEN** a Retrosheet `core.play` row is read
- **THEN** its Retrosheet game and event identifiers identify exactly one `raw.retrosheet_event` row

### Requirement: Rebuild is repeatable and lossless
Rebuilding the widened tables SHALL be idempotent and SHALL preserve the count of source rows.

#### Scenario: Run twice
- **WHEN** the build runs twice on the same raw data
- **THEN** the second run changes no rows

#### Scenario: Row parity
- **WHEN** the build finishes
- **THEN** `core.pitch` has one row per `raw.statcast_pitch` row, including rows whose game does not resolve (game key `NULL`)

### Requirement: Widening does not change what is publicly exported
Widened tables SHALL keep their existing export rights profile, and new `core` relations SHALL NOT be exported until registered with a rights profile.

#### Scenario: Existing profile kept
- **WHEN** the export allow-list is read after the widening
- **THEN** `core.pitch` and `core.play` are still `local_research`

#### Scenario: New relation not exported
- **WHEN** `core.play_retro` exists but is not registered in the allow-list
- **THEN** no export preset includes it
