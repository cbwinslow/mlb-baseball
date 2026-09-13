## MODIFIED Requirements

### Requirement: Source-rights gate at export time

The export SHALL check each table against the project's source-profile
rules before writing it. A table that is not eligible for public
distribution SHALL be excluded from the export, with the exclusion and
its reason recorded in the log and the manifest.

The export SHALL NOT publish a table whose eligibility is unknown;
unknown is treated as not eligible.

`mlb export --profile public_safe` SHALL include the Retrosheet-keyed
`gold.mart_*` research mart in addition to the already-eligible
Retrosheet event, gameinfo, run-expectancy, win-expectancy, and leverage
relations. It SHALL NOT include `gold.player_season`, `gold.team_season`,
`gold.division_standing`, `gold.game_export`, `gold.game_feature`,
`gold.fangraphs_*`, or Lahman postseason gold tables.

`mlb export --preset backbone` SHALL continue to export exactly the
eight publishable counting-stat backbone tables already reviewed
(`batting_game`, `pitching_game`, `batting_season`, `pitching_season`,
`batting_team`, `pitching_team`, `batting_career`, `pitching_career`),
excluding `player_season` and `team_season` on rights grounds. The
backbone preset SHALL NOT be extended with `gold.mart_*` in this change.

#### Scenario: An ineligible table is excluded with a recorded reason

- **WHEN** the export encounters a table whose source profile disallows
  public distribution
- **THEN** that table is not written to Parquet
- **AND** the manifest and log record the table name and the reason it
  was excluded

#### Scenario: The public-safe profile dumps the mart

- **WHEN** `mlb export --profile public_safe` runs on a database with
  populated `gold.mart_*` tables
- **THEN** those mart tables are written
- **AND** `gold.player_season` is not written

#### Scenario: The backbone preset does not absorb the mart

- **WHEN** `mlb export --preset backbone` runs
- **THEN** the output table set does not include `gold.mart_*`
- **AND** it still excludes `gold.player_season` and `gold.team_season`
