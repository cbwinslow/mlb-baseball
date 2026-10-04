## Purpose

Keep `core` identifiers permanent and rebuild `core` only for the seasons whose source data changed, so a normal night processes about one season and a republished historical season is reprocessed without a full rebuild.

## ADDED Requirements

### Requirement: Internal ids are permanent

A row in `core.team`, `core.player`, `core.venue` or `core.game` SHALL keep the same internal `id` across every `mlb conform` run for as long as the entity exists in the sources. New entities SHALL receive new ids. An id SHALL NOT be reused for a different entity.

#### Scenario: A second run does not change ids

- **WHEN** `mlb conform` runs twice with no change to the raw data in between
- **THEN** every `core.game.id`, `core.team.id`, `core.player.id` and `core.venue.id` is identical after the second run

#### Scenario: A player gains a Retrosheet id later

- **WHEN** a player admitted on an MLBAM id alone later appears in the register with a Retrosheet id
- **THEN** the same `core.player` row is updated with the Retrosheet id and keeps its `id`

#### Scenario: A game gains a source id

- **WHEN** a game that had only a Retrosheet id later matches an MLB `game_pk`
- **THEN** the same `core.game` row receives the `game_pk` and keeps its `id`

### Requirement: Only changed seasons are rebuilt

`mlb conform` SHALL record, for each season and each layer it builds, a fingerprint of the raw inputs used. A run SHALL rebuild a season when its recorded fingerprint differs from the current one, when it has no recorded fingerprint, or when it is the current season, and SHALL leave all other seasons untouched.

#### Scenario: A normal night

- **WHEN** only current-season raw rows changed since the last run
- **THEN** only the current season is rebuilt and the run reports the seasons it rebuilt and the seasons it skipped

#### Scenario: Retrosheet republishes an old season

- **WHEN** the raw rows of one past season are reloaded (for example `mlb ingest retrosheet_event --refresh`)
- **THEN** the next run rebuilds that season and no other past season

#### Scenario: Nothing changed

- **WHEN** no raw input changed and it is not a new season
- **THEN** the run rebuilds only the current season and exits successfully

### Requirement: Incremental and full rebuilds agree

`mlb conform --full` SHALL rebuild every season from scratch. For the same raw data, the rows produced by an incremental run SHALL equal the rows produced by a full run, ignoring surrogate id values and `_conformed_at` timestamps.

#### Scenario: Equivalence on a fixture

- **WHEN** an incremental run over a fixture that was built in two steps is compared with a full run over the same final raw data
- **THEN** per-table row counts and a content checksum of the natural-key columns match

### Requirement: Game matches are computed once

Linking a Retrosheet game to an MLB `game_pk` SHALL be attempted only for games that have no `game_pk` yet, and each stored link SHALL record the rule that produced it. Games that no rule matches SHALL remain unmatched with a null `game_pk`, never guessed.

#### Scenario: An existing match is kept

- **WHEN** a game already has a `game_pk` and a later run sees unchanged inputs
- **THEN** its `game_pk` and recorded rule are unchanged and no matching rule runs for it

#### Scenario: An unmatched game stays honest

- **WHEN** no matching rule links a game
- **THEN** its `game_pk` is null and it is listed in the run's unmatched count
