## ADDED Requirements

### Requirement: Every source has a verified inventory of what it offers
Each source page under `docs/sources/` SHALL list every endpoint, file or table the source offers with its fields, first valid year, request cost, and the raw table that stores it or the recorded reason it is not stored.

#### Scenario: An offered dataset has no table
- **WHEN** a source page lists an offered dataset with no raw table
- **THEN** it names a reason and an owning task, otherwise the docs check fails

### Requirement: Source schemas are snapshotted and compared
The system SHALL save a sample response or file header per offered dataset and, on each run, compare field names and types with the previous snapshot. The check SHALL be read-only toward the database and use at most one request per dataset.

#### Scenario: A source adds a field
- **WHEN** a response carries a field absent from the last snapshot
- **THEN** the run reports the dataset and field as added and exits non-zero without loading anything

#### Scenario: A source cannot be reached
- **WHEN** a request fails after retries
- **THEN** the dataset is reported as unchecked, not as unchanged

### Requirement: New offerings are surfaced
The system SHALL report an endpoint, file or board that appears at the source and is not in the inventory.

#### Scenario: A new file appears
- **WHEN** a publisher's file list contains a file not in the inventory
- **THEN** the report names it and links the task that must classify it as wanted, scope or unavailable
