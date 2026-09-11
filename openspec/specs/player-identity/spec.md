# player-identity Specification

## Purpose
Defines how a person becomes a row in `core.player`: which source keys admit a
player, when the Retrosheet id may be absent and what that absence means, and
the guarantee that every participant in a regular-season game is resolvable.

## Requirements

### Requirement: A player is admitted to `core.player` on the strongest identity available

The system SHALL admit a person from the Chadwick register
(`raw.register_people`) into `core.player` when **either** holds:

- the person has a Retrosheet id (`key_retro`); **or**
- the person has an MLBAM id (`key_mlbam`) **and** that MLBAM id appears in
  MLB's own game record — `raw.mlb_boxscore_batting`, `raw.mlb_boxscore_pitching`,
  or `raw.mlb_playbyplay` (as batter or pitcher).

The system SHALL NOT admit a person whose only identity is an MLBAM id and who
never appears in MLB game data — this deliberately excludes the ~100k
minor-league and foreign-league people the register carries.

Each admitted row SHALL carry every provider id the register has for that
person (`retro_id`, `mlbam_id`, `bbref_id`, `fangraphs_id`, `chadwick_uuid`),
with the absent ones null.

#### Scenario: A current-season debut with no Retrosheet id is admitted

- **WHEN** a player has appeared in a 2026 MLB box score, is present in `raw.register_people` with a `key_mlbam` but no `key_retro`
- **THEN** `core.player` has a row for that player, resolvable by `mlbam_id`
- **AND** that row's `retro_id` is null

#### Scenario: A minor-leaguer who never played an MLB game is not admitted

- **WHEN** a person in `raw.register_people` has a `key_mlbam`, no `key_retro`, and no appearance in `raw.mlb_boxscore_batting`, `raw.mlb_boxscore_pitching`, or `raw.mlb_playbyplay`
- **THEN** `core.player` has no row for that person

#### Scenario: A Retrosheet-era player is still admitted

- **WHEN** a person has a `key_retro`
- **THEN** `core.player` has a row for that person regardless of whether they appear in the MLB game tables

### Requirement: `retro_id` is nullable and a null means Retrosheet has not yet processed the player

`core.player.retro_id` SHALL be nullable. A null `retro_id` SHALL mean the
player was admitted on another identity (their MLBAM id) and Retrosheet's id is
expected to be assigned later, after Retrosheet processes that season.

`retro_id` SHALL remain unique across its non-null values (multiple null rows
are permitted).

A rebuild of `core.player` after Retrosheet has published ids for a season
SHALL populate `retro_id` for the players it previously admitted with a null,
with no manual step.

#### Scenario: retro_id backfills on the next rebuild

- **WHEN** a player was admitted in 2026 with a null `retro_id`, Retrosheet later assigns them a `key_retro` in `raw.register_people`, and `core.player` is rebuilt
- **THEN** that player's `core.player` row now has the assigned `retro_id`
- **AND** no duplicate `core.player` row was created for that player

#### Scenario: Two null-retro players do not collide

- **WHEN** two different current-season players are both admitted with a null `retro_id`
- **THEN** both have their own `core.player` row and the unique constraint on `retro_id` is not violated

### Requirement: Every regular-season game participant resolves to `core.player`

`mlb doctor` SHALL report a failure when any player appearing in
`raw.mlb_boxscore_batting` or `raw.mlb_boxscore_pitching` for a `core.game`
of type `regular` does not resolve to a `core.player` row by `mlbam_id`. The
tolerance SHALL be zero.

#### Scenario: An unresolved regular-season player fails the health check

- **WHEN** a player in a regular-season box score has no matching `core.player.mlbam_id` and `mlb doctor` runs
- **THEN** the check fails and names the count of unresolved player rows

#### Scenario: A fully resolved database passes the health check

- **WHEN** every regular-season box-score player resolves to `core.player` and `mlb doctor` runs
- **THEN** the check passes

### Requirement: Player admission is deterministic and idempotent

Rebuilding `core.player` over unchanged source data SHALL produce the same set
of rows with the same values (truncate-and-replace, transactional).

#### Scenario: A rebuild produces identical identity rows

- **WHEN** `core.player` is built twice against the same `raw.register_people` and MLB game tables
- **THEN** the two builds produce the same rows with the same provider ids
