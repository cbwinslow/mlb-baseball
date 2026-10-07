## ADDED Requirements

### Requirement: Repairs run only from a declared safe list
The system SHALL keep a list of repair commands marked safe (additive, idempotent, resumable, rate-limited). The self-repair step SHALL run only commands on that list and SHALL report every other gap without running anything.

#### Scenario: A gap needs an unsafe command
- **WHEN** coverage reports a gap whose fix is not on the safe list
- **THEN** the step lists it as needing the owner and runs nothing for it

### Requirement: Repair work is bounded and logged
Each self-repair run SHALL cap the work per source (items and wall time), record every command and its result in a `meta` table, and stop on repeated failure instead of retrying forever.

#### Scenario: A repair keeps failing
- **WHEN** the same repair fails three times in a row
- **THEN** it is suspended, reported, and not retried until the owner clears it

### Requirement: Repairs never disturb held data
A repair SHALL add only items the ledger or coverage shows as missing. Running it twice SHALL change nothing the second time.

#### Scenario: Run twice
- **WHEN** the repair step runs twice against the same database
- **THEN** the second run loads zero rows and edits none
