# Spec Delta

## Purpose
Raw source tables store values in their natural types, declared once and enforced at ingest, so a value is either stored exactly as the source gave it or the load says why not.

## ADDED Requirements

### Requirement: Types are declared per table
Every migrated raw table SHALL have a reviewed schema file naming each column's PostgreSQL type, and ingest SHALL cast to those types.

#### Scenario: A declared column
- **WHEN** a batch is landed
- **THEN** each declared column holds its declared type and an empty source value is NULL, never zero

### Requirement: No silent value changes
A value SHALL NOT be changed or dropped by type handling without a record.

#### Scenario: Source text "NA"
- **WHEN** a text column contains the source value `NA`
- **THEN** the stored value is `NA`, not NULL

#### Scenario: A value breaks its type
- **WHEN** a snapshot value cannot be cast to its declared type
- **THEN** the load stops and names the table, column and value, and nothing is written

### Requirement: Retype is proven before the swap
An existing table SHALL be replaced by its typed version only after a value-by-value comparison against the old table, with every difference listed.

#### Scenario: Comparison
- **WHEN** the typed and the old table are compared
- **THEN** row counts match and each differing cell is explained (a known old-path corruption) or the swap does not proceed

### Requirement: The old table is kept until approved
The replaced table SHALL stay (renamed) until the owner approves dropping it.

#### Scenario: Rollback
- **WHEN** a problem is found after a swap
- **THEN** renaming the tables back restores the old state with no data repair
