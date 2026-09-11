## ADDED Requirements

### Requirement: Game-type scope is explicit, not assumed

Every backbone relation, every other `gold` relation, every view, every
`mlb doctor` metric, and every math / ML model feature that aggregates
game-level performance SHALL scope `core.game.game_type` explicitly at build
time — regular-season relations filter to the regular-season type (and the
Game 163 tiebreaker), postseason relations filter to the postseason types. A
relation SHALL NOT rely on a source table (raw or conformed) being implicitly
free of other game types.

This follows baseball.computer's `seed_game_types` convention:
`RegularSeason` and `TiebreakerPlayoff` are regular season; `WildCardSeries`,
`DivisionSeries`, `LeagueChampionshipSeries`, `WorldSeries`, and
`OtherChampionship` are postseason and are excluded from regular-season
aggregates.

This applies to the existing backbone (already regular-season scoped) and is a
standing rule for any new relation or feature: the audit that lands with this
requirement records, per relation / feature, which `game_type`s it includes and
where the filter is.

#### Scenario: A new gold relation declares its game-type scope

- **WHEN** a new `gold` relation that aggregates game data is added
- **THEN** its build logic contains an explicit `game_type` filter
- **AND** its table contract states which game types it covers

#### Scenario: The regular-season backbone excludes a postseason game

- **WHEN** the backbone season relations are built for a season with a completed postseason
- **THEN** no postseason game contributes to any regular-season backbone row

#### Scenario: A model feature excludes postseason performance

- **WHEN** a math or ML model feature aggregates player or team game-level data over a season or a pre-game window
- **THEN** only regular-season (and Game 163) games contribute to it
