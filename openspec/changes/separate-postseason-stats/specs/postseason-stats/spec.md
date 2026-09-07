## Purpose

Separate, Retrosheet-event-derived postseason batting and pitching statistics —
kept apart from the regular-season backbone the way every upstream source keeps
them apart — so a researcher can study playoff performance without it
contaminating season numbers.

## ADDED Requirements

### Requirement: Postseason statistics live in their own relations

The system SHALL provide postseason batting and pitching statistic relations at
the player-season, team-season, and career grains, distinct from the
regular-season relations. They SHALL be built from the already-ingested
postseason source data (`raw.lahman_batting_post` / `raw.lahman_pitching_post` —
Lahman's `BattingPost` / `PitchingPost`), conforming player and team
identifiers to the project's `core` dimensions, and SHALL retain the source's
`round` (wild card / division series / league championship series / World
Series / pre-division-era pennant playoff).

Each postseason relation SHALL carry one row per `(player, season, round)` plus
one combined all-rounds row per `(player, season)`; the team grain the same at
`(team, season)`; the career grain one row per player summing their postseason
seasons.

An unresolved source identifier SHALL be reported by a health check, never
silently dropped.

#### Scenario: A player's postseason run is queryable separately

- **WHEN** a researcher queries the postseason batting relation for a player who reached the World Series
- **THEN** they get one combined row covering that player's whole postseason plus a row per round
- **AND** that player's regular-season line in `gold.player_season` / `gold.batting_season` is unchanged and contains none of those games

### Requirement: Regular-season relations never contain postseason games

`gold.player_season`, `gold.team_season`, `gold.batting_season` /
`gold.pitching_season` (and the game / team / career grains), and every
`gold` relation that aggregates game-level performance, SHALL count regular-season
games only. A relation SHALL scope `game_type` explicitly at build time rather
than relying on a source table being "clean".

The raw Baseball-Reference ingest (`raw.bref_batting` / `raw.bref_pitching`)
SHALL be regular-season only: the Baseball-Reference query SHALL end at the
regular-season boundary, not extend through the postseason.

#### Scenario: A playoff-team player's season line is regular season only

- **WHEN** `gold.player_season` is rebuilt after the fix, for a player whose team won the World Series
- **THEN** their games / plate appearances / counting stats match the player's official regular-season line
- **AND** none of their postseason games are included

#### Scenario: The raw Baseball-Reference ingest excludes the postseason

- **WHEN** `raw.bref_batting` is loaded for a season with a completed postseason
- **THEN** a deep-playoff-team player's row shows their regular-season game count, not regular + postseason

### Requirement: A doctor check guards against postseason contamination

`mlb doctor` SHALL fail if any `gold.player_season` / `gold.team_season` row
reports a game count or plate-appearance total beyond a plausible regular-season
envelope (a single team plays at most 162 regular-season games), and SHALL fail
if a postseason relation contains any game whose `game_type` is not a postseason
type.

#### Scenario: Contamination is caught by the health check

- **WHEN** a `gold.player_season` row reports more than the regular-season game envelope allows
- **THEN** `mlb doctor` reports a failure naming the row

#### Scenario: A misfiled game in a postseason relation is caught

- **WHEN** a row in `gold.batting_postseason` traces to a `game_type = 'regular'` game
- **THEN** `mlb doctor` reports a failure
