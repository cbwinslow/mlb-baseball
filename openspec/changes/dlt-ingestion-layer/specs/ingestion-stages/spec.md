# Spec Delta

## Purpose
Defines how a data source is split into separate download, load and check stages with narrow interfaces, so that any stage or tool can be replaced without changing what lands in the database or breaking another stage.

## ADDED Requirements

### Requirement: Stages are separable
A source SHALL be built from a download stage, a load stage and a check stage, each usable and testable without running the others. One stage SHALL NOT depend on another stage's internals.

#### Scenario: Replacing the download method
- **WHEN** the way a source is fetched is replaced and the fetched content is identical
- **THEN** the rows landed in `raw` are identical to those landed before the replacement

#### Scenario: Running a stage alone
- **WHEN** the load stage is run against an already downloaded artifact
- **THEN** it completes without any network access

### Requirement: Downloads are kept and replayable
The download stage SHALL keep every fetched artifact with its source URL, retrieval time, size and content hash, so the load stage can be re-run later from the kept copy.

#### Scenario: Reload after a parser change
- **WHEN** a parser is corrected and the source is reloaded
- **THEN** it reloads from the kept artifacts without refetching them

### Requirement: Raw stays source-faithful
Landed table and column names SHALL be the names the source provides (syntactically made safe only), and no tool-private tables or columns SHALL appear in the `raw`, `core` or `gold` schemas.

#### Scenario: Source field with mixed case
- **WHEN** a source field is named `clobTokenIds`
- **THEN** the landed column keeps the source spelling, lowercased only as the project's existing raw rule already requires

### Requirement: Loads are idempotent
Running a load twice over the same input SHALL leave the table contents identical after the second run.

#### Scenario: Second run
- **WHEN** a source is loaded twice from the same artifact
- **THEN** the second run reports zero rows written and the table is unchanged

### Requirement: The ingestion ledger is the record of what is done
`meta.ingestion_item` SHALL remain the record of which items are loaded, unavailable or failed. State held by a tool for its own use SHALL be rebuildable from the ledger and the kept artifacts.

#### Scenario: Tool state is lost
- **WHEN** a tool's local state is deleted
- **THEN** the next run resumes from the ledger, repeats no completed item, and creates no duplicate rows

### Requirement: Rights profiles are enforced outside the tools
A source's rights profile SHALL be applied by the project's own code regardless of which tool downloaded or loaded the data.

#### Scenario: Export of a restricted source
- **WHEN** an export is requested for a source whose profile forbids redistribution
- **THEN** the export refuses, whichever tool landed the data

### Requirement: Source changes are visible
A new, removed or retyped source field SHALL be recorded and reported, and SHALL NOT be silently dropped or silently accepted. A value that cannot be typed SHALL be kept as source text in a reject table.

#### Scenario: New field appears
- **WHEN** a source adds a field
- **THEN** the field is landed as a new text column, and `mlb schema-watch` reports it

### Requirement: Failures name the failed item
A failed fetch or load SHALL be recorded against the item that failed, SHALL keep progress already made, and SHALL fail the run at the end if any item failed.

#### Scenario: One window fails
- **WHEN** one of many items fails
- **THEN** the others complete and are recorded, the failed item is recorded as failed, and the run exits non-zero
