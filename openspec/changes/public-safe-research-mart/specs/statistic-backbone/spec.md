## MODIFIED Requirements

### Requirement: Backbone relations are `local_research`, not `public_safe`

Every backbone relation (`gold.batting_game`, `gold.pitching_game`,
`gold.batting_season`, `gold.pitching_season`, `gold.batting_team`,
`gold.pitching_team`, `gold.batting_career`, `gold.pitching_career`)
SHALL remain registered in the `mlb export` allow-list with the
`local_research` profile, because its builder joins the conformed
`core` dimensions (which mix non-Retrosheet sources) for surrogate keys,
and `public_safe` admits Retrosheet-only lineage.

The public-safe variant keyed by Retrosheet identifiers SHALL be the
`gold.mart_*` surface defined by the `public-safe-mart` spec, not a
reclassification of these backbone relations. `gold.player_season` and
`gold.team_season` SHALL remain the Baseball-Reference / Lahman official
lines (ADR-281) and SHALL remain ineligible for public-safe export.

#### Scenario: A backbone relation is excluded from the public-safe bundle

- **WHEN** the public-safe export profile runs
- **THEN** the core-keyed backbone relations are not included, and the
  exclusion reason (core-dimension lineage) is recorded

#### Scenario: The Retrosheet-keyed mart is what public-safe ships instead

- **WHEN** the public-safe export profile runs against a built mart
- **THEN** `gold.mart_player_game` / `gold.mart_player_season` /
  `gold.mart_team_season` (and the mart identity tables) are included
- **AND** `gold.batting_game` / `gold.player_season` are not
