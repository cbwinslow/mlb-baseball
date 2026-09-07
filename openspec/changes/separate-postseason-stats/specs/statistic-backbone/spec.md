## ADDED Requirements

### Requirement: Game-type scope is explicit, not assumed

Every backbone relation and every other `gold` relation that aggregates
game-level performance SHALL scope `core.game.game_type` explicitly at build
time — regular-season relations filter to the regular-season type, postseason
relations filter to the postseason types. A relation SHALL NOT rely on a source
table (raw or conformed) being implicitly free of other game types.

This applies to the existing backbone (already regular-season scoped) and is a
standing rule for any new relation: the audit that lands with this requirement
records, per relation, which `game_type`s it includes and where the filter is.

#### Scenario: A new gold relation declares its game-type scope

- **WHEN** a new `gold` relation that aggregates game data is added
- **THEN** its build logic contains an explicit `game_type` filter
- **AND** its table contract states which game types it covers

#### Scenario: The regular-season backbone excludes a postseason game

- **WHEN** the backbone season relations are built for a season with a completed postseason
- **THEN** no postseason game contributes to any regular-season backbone row
