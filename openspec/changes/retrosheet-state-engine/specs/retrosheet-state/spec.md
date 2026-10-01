## Purpose

Defines the game-state layer of the Retrosheet Python package: turning an event
file's records into one event row per play with outs, runners, score and fielding
credit, and proving those rows equal to Chadwick's `cwevent` output.

## ADDED Requirements

### Requirement: One event row per play with state before and after

The package SHALL walk the records of each game in file order and produce one
event row per play record, carrying the inning, batting side, outs, base occupancy
and score before the play, the batter and runner destinations, and the outs and
runs the play produced. Lineup and defensive changes (`start`, `sub`, and
adjustment records) SHALL be applied before the plays that follow them.

#### Scenario: Plays advance the game state

- WHEN a game is processed from its first record to its last
- THEN each row's before-state equals the previous row's after-state within a
  half-inning, and a half-inning ends on the third out

#### Scenario: Substitutions are visible to later plays

- WHEN a pinch runner or pinch hitter enters before a play
- THEN that play's row names the new player in the matching base, batter and
  defensive fields

### Requirement: Output equals Chadwick cwevent

For every event file in a validated season, the rows SHALL equal Chadwick
`cwevent` 0.10.0 output field by field for fields `-f 0-96` and `-x 0-66`, with
the exceptions below. Equality SHALL be checked by running both on the same file
and comparing whole rows; no field may be skipped silently.

Fields that depend on files outside the event file (for example team or roster
data) SHALL be named in a published list of exclusions. Any other difference SHALL
fail validation.

#### Scenario: A validated season matches

- WHEN a validated season's files are run through the engine and through
  `cwevent`
- THEN every compared row is identical in every compared field and the report
  shows 0 mismatches and 0 misaligned games

#### Scenario: A column is missing from either side

- WHEN a compared column is absent from the reference output or from ours
- THEN validation fails with the column name instead of skipping it

#### Scenario: A season cannot reach zero

- WHEN a season still has mismatches after the known rules are applied
- THEN the report lists the season, field counts and example plays, and the
  season is not recorded as validated

### Requirement: Unknown or unsupported play syntax is never absorbed

If a play cannot be interpreted well enough to update the state (an unsupported
modifier, an impossible runner movement, a fielding credit that cannot be
assigned), the engine SHALL raise an error naming the game, line and play text in
strict mode, or emit an explicit unsupported marker on that row in diagnostic
mode. It SHALL NOT guess the state change or continue as if the play were
understood.

#### Scenario: Impossible runner movement

- WHEN a play moves a runner from a base that is empty
- THEN strict mode raises an error that names the game and line

#### Scenario: Diagnostic mode keeps going visibly

- WHEN diagnostic mode meets an unsupported play
- THEN the row is flagged unsupported, the count appears in the coverage report,
  and later rows in that game are marked as depending on an uncertain state

### Requirement: The B and B1S modifiers are resolved explicitly

The 48 plays using the `B` and `B1S` modifiers in the 1976 data SHALL either be
handled with behaviour that matches Chadwick's output for those plays, or be
reported as unsupported under the rule above. They SHALL NOT be dropped.

#### Scenario: 1976 modifier plays

- WHEN the 1976 season is processed
- THEN each `B` or `B1S` play appears in the output equal to Chadwick, or in the
  unsupported report with its text

### Requirement: The state layer stays independent

The state layer SHALL import only the Python standard library and `retrosheetpy`
itself. It SHALL NOT import `mlb_baseball`, a dataframe library, a database
driver or native code, and SHALL NOT require Chadwick at run time (Chadwick is a
development-time reference only).

#### Scenario: Clean import

- WHEN the package is imported in a clean environment
- THEN none of `mlb_baseball`, pandas, psycopg or a Chadwick binary is loaded or
  needed
