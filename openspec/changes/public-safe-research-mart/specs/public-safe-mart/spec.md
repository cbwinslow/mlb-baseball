## Purpose

Gives an outside analyst a Retrosheet-keyed player, team, and game query
surface they can dump under the project's public-safe rights profile —
counting stats plus the cited advanced rates issue #89 asked for —
without redistributing Baseball-Reference, Lahman, FanGraphs, Statcast,
or MLB Stats API content.

## ADDED Requirements

### Requirement: A public-safe mart exists at player, team, and game grains

The system SHALL materialize a reporting mart in `gold` with at least:

- `gold.mart_player` — one row per Retrosheet player identifier;
- `gold.mart_team` — one row per Retrosheet team-era identifier;
- `gold.mart_game` — one row per Retrosheet regular-season game identifier;
- `gold.mart_player_game` — one batting or pitching line per
  `(retro_game_id, retro_id, retro_team_id, role)`;
- `gold.mart_player_season` — stint lines plus exactly one combined
  full-season line per `(retro_id, season, role)`;
- `gold.mart_team_season` — one row per `(retro_team_id, season)`.

Keys SHALL be Retrosheet identifiers, never `core.player.id` /
`core.team.id` / `core.game.id`. A two-way player SHALL have both a
`batting` and a `pitching` role row at the game and season grains.

Coverage of the fact tables SHALL be regular-season Retrosheet events
from 1910 through the last season Retrosheet has published as event
files. Rows derived from MLB box scores, Statcast, Baseball-Reference,
Lahman, FanGraphs, or Chadwick SHALL NOT appear.

#### Scenario: A stranger queries a player-season without core surrogate keys

- **WHEN** `gold.mart_player_season` is queried for a known Retrosheet
  player id and a season covered by Retrosheet events
- **THEN** a combined full-season row is returned keyed by that
  Retrosheet id
- **AND** the row has no `core.player.id` column

#### Scenario: A two-way player has both roles

- **WHEN** a player both batted and pitched in a game in the mart
- **THEN** `gold.mart_player_game` contains a `batting` row and a
  `pitching` row for that `(retro_game_id, retro_id)`

#### Scenario: A 2026 MLB box-score game is absent from the mart

- **WHEN** the mart is built from a database that also has
  `gold.batting_game` rows with `source = 'mlb_boxscore'`
- **THEN** no `gold.mart_player_game` row exists for those games

### Requirement: Mart builders use only Retrosheet lineage

Mart build SQL SHALL read Retrosheet raw products (and
`gold.run_expectancy_24`, which is itself Retrosheet-derived and already
`public_safe`) and SHALL NOT join `core.*`, `raw.bref_*`, `raw.lahman_*`,
`raw.statcast*`, `raw.mlb_*`, or `raw.fangraphs_*`. Game-type scope SHALL
be an explicit filter on Retrosheet gameinfo (regular season, including
the Game 163 tiebreaker).

#### Scenario: Build SQL does not reference a non-Retrosheet source

- **WHEN** the mart SQL resources are scanned
- **THEN** they contain no identifiers for `core.`, Baseball-Reference,
  Lahman, Statcast, MLB API, or FanGraphs schemas/tables

### Requirement: Advanced stats are cited, additive, and null-honest

`gold.mart_player_game` and `gold.mart_player_season` SHALL carry, at
minimum, wOBA, FIP (pitching role), RE24, wSB (batting role), K%, BB%,
GB%, FB%, and LD%, plus the additive components needed to recompute
those rates at coarser grains.

- wOBA SHALL use the project's published fixed modern linear weights
  applied to Retrosheet event classification, not `gold.fangraphs_guts`.
- FIP SHALL use a seasonal constant computed from Retrosheet events so
  league FIP equals league RA9; it SHALL NOT use FanGraphs `cfip` and
  SHALL NOT invent earned runs.
- RE24 SHALL be the sum of `gold.run_expectancy_24` changes on charged
  events.
- wSB SHALL be computed from Retrosheet steal flags with a cited linear
  weight; it SHALL NOT wait on a Baseball-Reference steal total.
- GB%/FB%/LD% SHALL use Retrosheet `battedball_cd` and SHALL be null
  when no coded batted ball in play exists (including typical pre-1988
  missingness).
- Every rate SHALL be null on a zero denominator, never zero-filled and
  never averaged from a finer grain's rates.
- Statcast location and expected-stat columns (`hc_x`, `hc_y`,
  `launch_speed`, `xwoba`, and kin) SHALL NOT exist on any mart table.

Season and team rates SHALL be recomputed from summed numerators and
denominators.

#### Scenario: A zero-PA line does not report a fake wOBA

- **WHEN** a player-game batting row has zero wOBA denominator
- **THEN** `woba` is null and is not zero

#### Scenario: FIP is not a FanGraphs guts lookup

- **WHEN** the mart is built
- **THEN** no mart builder reads `gold.fangraphs_guts` or
  `gold.fangraphs_park_factors`
- **AND** league FIP for a Retrosheet season equals that season's league
  RA9 within the documented rounding tolerance

#### Scenario: A Statcast spray-chart column cannot land on the mart

- **WHEN** a mart table is inspected for column names
- **THEN** it has no `hc_x`, `hc_y`, or Statcast expected-stat columns

### Requirement: The public-safe dump includes the mart and excludes rights-gated gold

`mlb export --profile public_safe` SHALL write the mart tables (and the
already-public Retrosheet event / gameinfo / RE24 / WE / LI relations)
and SHALL NOT write `gold.player_season`, `gold.team_season`,
`gold.division_standing`, `gold.game_export`, `gold.game_feature`,
`gold.fangraphs_*`, or Lahman postseason gold tables.

`mlb export --preset backbone` SHALL remain the eight counting-stat
tables already published; it SHALL NOT gain mart tables and SHALL NOT
gain `gold.player_season` / `gold.team_season`.

#### Scenario: public_safe export contains the mart

- **WHEN** `mlb export --profile public_safe` runs against a database
  with a populated mart
- **THEN** the output includes each `gold.mart_*` table
- **AND** the manifest records them as public-safe with Retrosheet
  attribution

#### Scenario: public_safe export still excludes Baseball-Reference season lines

- **WHEN** `mlb export --profile public_safe` runs
- **THEN** it does not write `gold.player_season` or `gold.team_season`
- **AND** the exclusion reason remains rights, not a silent skip

#### Scenario: backbone preset is unchanged by the mart

- **WHEN** `mlb export --preset backbone` runs
- **THEN** the written table set is still the eight counting-stat
  backbone files
- **AND** no `mart_*` file is added to that preset

### Requirement: Doctor fails closed on an empty or contaminated mart

After `mlb report`, `mlb doctor` SHALL fail if a mart fact table has
zero rows while `raw.retrosheet_event` has rows, or if a mart table
carries a denylisted Statcast column name, or if a mart row's source is
not a Retrosheet product.

#### Scenario: An empty mart on a loaded event table fails doctor

- **WHEN** `raw.retrosheet_event` has rows and `gold.mart_player_game`
  has zero rows
- **THEN** `mlb doctor` reports a failure naming that mart table

### Requirement: Public query recipes use the mart

Documented stranger-facing query recipes SHALL use `gold.mart_*` for
player, team, and game examples. Recipes against `gold.player_season`,
`gold.team_season`, `gold.division_standing`, or `gold.game_export`
SHALL be labelled local-research and not-for-redistribution.

#### Scenario: The public runbook does not tell a stranger to dump BRef

- **WHEN** the public section of `docs/RESEARCH_QUERY_RUNBOOK.md` is
  read
- **THEN** its worked examples query `gold.mart_*`
- **AND** they do not present `gold.player_season` as redistributable
