## Purpose

Defines the read-only check that proves the redundant Retrosheet sources agree
with each other and that `core` is populated correctly from them, and the
evidence required that ingestion tests prove what they claim.

## ADDED Requirements

### Requirement: The tie-out gate never changes data

The tie-out gate SHALL only read from `raw`, `core` and `gold`. It SHALL NOT
insert, update, delete, truncate or alter any table in those schemas, and SHALL
refuse to run against a database it cannot confirm is read-only safe to query.

#### Scenario: The gate is run against production

- **WHEN** the gate runs against production `mlb`
- **THEN** it issues only read queries
- **AND** no table's row count or contents change

### Requirement: Redundant sources are compared at season, game and player-game level

For every season where at least two independent Retrosheet sources cover the
same fact, the gate SHALL compare them at season totals, per game, and per
player-game for plate appearances, strikeouts, walks, home runs, runs and game
counts. The sources are the Chadwick-parsed event files, Retrosheet's CSV
play-by-play, its per-player batting CSVs, the game logs (regular season and
postseason files), and the box scores where they exist.

#### Scenario: Two sources agree

- **WHEN** two sources are compared for a season and every compared count is
  equal
- **THEN** the season passes for that pair and the counts are recorded

#### Scenario: Two sources disagree without an explanation

- **WHEN** a compared count differs and the difference is not in the
  explained-differences register
- **THEN** the gate exits with a non-zero status
- **AND** the report names the season, game or player, the sources and both values

#### Scenario: Sources do not overlap

- **WHEN** a season has only one source for a fact
- **THEN** the gate reports "not comparable" for that season
- **AND** does not report it as a pass

### Requirement: Differences are explained, never silently accepted

Every difference the gate tolerates SHALL appear in an explained-differences
register with its cause, the seasons it applies to, and the evidence. The gate
SHALL treat any difference outside the register as a failure. A pass mark for
each comparison SHALL be committed before the gate is run against the full
history.

#### Scenario: A known difference

- **WHEN** game-log home runs are lower than event home runs by exactly the
  postseason total in the postseason game-log file
- **THEN** the gate reports the difference as explained, citing that register
  entry

#### Scenario: A difference matches no entry

- **WHEN** a difference does not match any register entry
- **THEN** it is reported as unexplained and fails the gate

### Requirement: The core layer is complete and faithful to raw

The gate SHALL confirm that `core.play` and `core.game` contain every play and
game their raw sources supply for the compared seasons, with no duplicates and
no rows absent from raw, and that key attributes copied into `core` equal the
raw values.

#### Scenario: core matches raw

- **WHEN** plate-appearance counts and game counts are compared between raw and
  `core` for a season
- **THEN** they are equal, or the difference is in the register

#### Scenario: conform dropped or duplicated rows

- **WHEN** `core` has fewer, more or duplicated rows than raw for a season
- **THEN** the gate fails and names the season and counts

### Requirement: Column names are pinned to the source contract

Tests SHALL fail when a raw Retrosheet table's column names differ from the
documented source contract (the installed Chadwick field list for event and
game tables, the published CSV headers for CSV tables), so that a silent field
shift cannot pass unnoticed.

#### Scenario: A field list drifts

- **WHEN** the parsed field list for a raw table no longer matches the pinned
  contract
- **THEN** the test fails and names the differing columns

### Requirement: Player identities in events resolve to rosters

Every batter and pitcher identifier in the event files SHALL exist in the
Retrosheet rosters or the all-players reference for the compared seasons.
Unresolved identifiers SHALL be listed, not dropped.

#### Scenario: An identifier is missing

- **WHEN** an event batter or pitcher identifier has no roster or all-players row
- **THEN** it is reported with its season and count

### Requirement: Ingestion tests are audited and gaps are recorded

The change SHALL record, for each Retrosheet raw table, which behaviors the
existing tests prove (row landing, reload-replaces-own-scope, missing input,
column count, content correctness) and which they do not. Gaps that could hide
incorrect data SHALL be closed by tests or listed with an issue.

#### Scenario: The audit is read

- **WHEN** a reviewer opens the audit record
- **THEN** each raw Retrosheet table shows its proven behaviors, its unproven
  behaviors, and the test or issue that covers each unproven one

### Requirement: The gate is proven to detect problems

The gate's own tests SHALL show that a fixture with a planted mismatch fails
and that a matching fixture passes, using the repository's disposable test
databases.

#### Scenario: A mismatch is planted

- **WHEN** a fixture has one strikeout removed from one source
- **THEN** the gate fails and reports that game

#### Scenario: A clean fixture

- **WHEN** a fixture has identical counts in every source
- **THEN** the gate passes
