## Purpose

Defines the internal-research relations conformed from `raw.fangraphs_*`: which
`gold.*` / `feat.*` relations exist, at what grain, from which raw source, how
identities resolve, the point-in-time semantics for projections, the
`local_research` rights posture that must hold for every one of them, and the
health signals a maintainer watches. It does not change the public statistic
backbone.

## ADDED Requirements

### Requirement: FanGraphs-derived relations are internal-research only

Every relation this capability introduces (`gold.fangraphs_guts`,
`gold.fangraphs_park_factors`, `feat.fangraphs_projection`, and any later
addition) SHALL be treated as `local_research`. None SHALL be registered as a
`public_safe` export or serve relation, appear in the published `mlb-research`
dataset, or be an input to the reference baseline model. The rights guard SHALL
fail closed: a test SHALL assert no `gold.fangraphs_*` relation carries a
`public_safe` profile in the export/serve registry.

#### Scenario: A FanGraphs-derived relation is proposed for public export

- **WHEN** the export/serve relation registry is checked
- **THEN** no relation whose name begins `gold.fangraphs_` (or the
  `feat.fangraphs_*` relations) is marked `public_safe`
- **AND** the check is part of the test suite, not a manual review step

### Requirement: Per-season wOBA / FIP constants are conformed verbatim

`gold.fangraphs_guts` SHALL carry one row per season from `raw.fangraphs_guts`,
with the linear weights and constants (`woba`, `wobascale`, `wbb`, `whbp`,
`w1b`, `w2b`, `w3b`, `whr`, `runsb`, `runcs`, `r_pa`, `r_w`, `cfip`) cast to a
numeric type. Source values SHALL be preserved exactly — no re-derivation, no
interpolation of missing seasons. `season` is the key; re-running the build
SHALL produce identical rows.

This relation is a **reference / cross-check**. A wОBA or FIP figure the
project publishes SHALL be computed from the project's own `core` data, not
from `gold.fangraphs_guts`; the join is for era-accurate *internal* work only.

#### Scenario: Constants are available per season

- **WHEN** `gold.fangraphs_guts` is queried for a given season FanGraphs covers
- **THEN** exactly one row is returned with every weight column populated
- **AND** the values equal `raw.fangraphs_guts` for that season

### Requirement: Park factors are conformed to core.team per season

`gold.fangraphs_park_factors` SHALL carry one row per `(season, team)` from
`raw.fangraphs_park_factors`, with `team` resolved to a `core.team` identifier
by the same team-code resolution the conformance layer already uses. The basic
and component factors SHALL be kept as the source publishes them. A team code
that does not resolve SHALL be reported by a health check, never silently
dropped or guessed.

#### Scenario: An unresolved FanGraphs team code

- **WHEN** a `raw.fangraphs_park_factors` row carries a team code with no
  `core.team` match
- **THEN** the build does not write a row with a null or guessed team
- **AND** `mlb doctor` reports the unresolved code with enough detail to fix
  the team-alias table

### Requirement: Projections conform into the feature store with as-of semantics

`feat.fangraphs_projection` SHALL be a DuckDB `feat.*` relation built by
`mlb build`, one row per `(projection_system, stat_group, player_id,
captured_date)`, `player_id` resolved to `core.player`. `captured_date` is the
availability timestamp. A projection row SHALL be a valid pre-event input only
for games whose date is on or after its `captured_date`; the relation SHALL be
shaped so an as-of retrieval ("the projection as known on date D") selects the
latest `captured_date <= D` per key without scanning future snapshots.

Projections SHALL NOT be conformed into `gold` — they are model inputs, not
research facts (ADR-287).

#### Scenario: As-of retrieval never sees a future projection

- **WHEN** `feat.fangraphs_projection` is queried for a player's projection as
  known on date D
- **THEN** the row returned has the greatest `captured_date` that is `<= D`
- **AND** no row with `captured_date > D` influences the result

### Requirement: Builds skip cleanly without the FanGraphs raw tables

Each build (`gold.fangraphs_guts`, `gold.fangraphs_park_factors`,
`feat.fangraphs_projection`) SHALL pre-check its `raw.fangraphs_*` source and
skip without error when it is absent, so `mlb report` / `mlb build` on a
database that never ingested FanGraphs behave exactly as before this change.
Re-running any build SHALL be idempotent (truncate-and-replace for the `gold`
relations; the `feat` relation rebuilt whole from the current raw snapshots).

#### Scenario: A database without FanGraphs

- **WHEN** `mlb report` runs on a database with no `raw.fangraphs_guts`
- **THEN** `gold.fangraphs_guts` is not created or is left untouched, no error
  is raised, and every other `gold` relation builds normally

### Requirement: Health checks cover coverage and identity

`mlb doctor` SHALL report, for this capability: row counts for the three
relations; `core.team` / `core.player` join coverage for
`gold.fangraphs_park_factors` and `feat.fangraphs_projection`; and that
`gold.fangraphs_guts` has a row for every season present in
`gold.batting_season` from 2002 onward (the modern span FanGraphs' Guts! table
covers). A shortfall SHALL be actionable (which seasons / codes / ids).

#### Scenario: A missing modern-season constant

- **WHEN** `gold.batting_season` has a 2019 season but `gold.fangraphs_guts`
  does not
- **THEN** `mlb doctor` flags 2019 as a missing FanGraphs constant row
