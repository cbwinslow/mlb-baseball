# fangraphs-conform Specification

## Purpose

Defines the internal-research reference relations conformed from `raw.fangraphs_*`
in **Beat 1**: which `gold.*` relations exist, at what grain, from which raw
source, how team identity resolves, the `season >= 2003` park-factor scope, the
`local_research` rights posture that must hold for every one of them, and the
health signals a maintainer watches. It does not change the public statistic
backbone. FanGraphs projections (`feat.fangraphs_projection`) are a named Beat 2
deferral and are out of scope here.

## Requirements

### Requirement: FanGraphs-derived relations are internal-research only

Every relation this capability introduces (`gold.fangraphs_guts`,
`gold.fangraphs_park_factors`, and any later addition) SHALL be treated as
`local_research`. None SHALL be registered as a `public_safe` export relation,
appear in the published `mlb-research` dataset, or be an input to the reference
baseline model. The rights guard SHALL fail closed: a test SHALL assert no
relation whose name begins `gold.fangraphs_` carries a `public_safe` profile in
the export relation registry, and SHALL assert `require_sources` still rejects
the `fangraphs` source under any non-`local_research` profile.

#### Scenario: A FanGraphs-derived relation is proposed for public export

- **WHEN** the export relation registry is checked
- **THEN** no relation whose name begins `gold.fangraphs_` is marked
  `public_safe`, and none appears in the backbone publish preset
- **AND** the check is part of the test suite, not a manual review step

### Requirement: Per-season wOBA / FIP constants are conformed verbatim

`gold.fangraphs_guts` SHALL carry one row per season from `raw.fangraphs_guts`,
with the linear weights and constants (`woba`, `wobascale`, `wbb`, `whbp`,
`w1b`, `w2b`, `w3b`, `whr`, `runsb`, `runcs`, `r_pa`, `r_w`, `cfip`) cast to a
numeric type. Source values SHALL be preserved exactly — no re-derivation, no
interpolation of missing seasons. `season` is the key; re-running the build
SHALL produce identical rows.

This relation is a **reference / cross-check**. A wOBA or FIP figure the
project publishes SHALL be computed from the project's own `core` data, not
from `gold.fangraphs_guts`; the join is for era-accurate *internal* work only.

#### Scenario: Constants are available per season

- **WHEN** `gold.fangraphs_guts` is queried for a given season FanGraphs covers
- **THEN** exactly one row is returned with every weight column populated
- **AND** the values equal `raw.fangraphs_guts` for that season

### Requirement: Park factors are conformed to core.team per season, 2003 onward

`gold.fangraphs_park_factors` SHALL carry one row per `(season, team_id)` from
`raw.fangraphs_park_factors` for `season >= 2003`, with `team` (a FanGraphs
nickname) resolved to a `core.team` identifier through the `core.team_alias`
crosswalk the conformance layer already owns, extended with a `'fangraphs'`
source block. The basic and component factors SHALL be kept as the source
publishes them. A nickname that does not resolve SHALL be reported by a health
check, never silently dropped or guessed. Pre-2003 rows SHALL remain only in
`raw` (low value, unstable franchise set).

#### Scenario: An unresolved FanGraphs team nickname

- **WHEN** a `raw.fangraphs_park_factors` row (`season >= 2003`) carries a
  nickname with no `core.team_alias` match
- **THEN** the build does not write a row with a null or guessed team
- **AND** `mlb doctor` reports a shortfall with enough detail to fix the
  team-alias seed

#### Scenario: A pre-2003 park-factor row

- **WHEN** `raw.fangraphs_park_factors` has a row for a season before 2003
- **THEN** no corresponding row is written to `gold.fangraphs_park_factors`

### Requirement: Builds skip cleanly without the FanGraphs raw tables

Each build (`gold.fangraphs_guts`, `gold.fangraphs_park_factors`) SHALL
pre-check its `raw.fangraphs_*` source and skip without error when it is
absent, so `mlb report` on a database that never ingested FanGraphs behaves
exactly as before this change. Re-running any build SHALL be idempotent
(truncate-and-replace).

#### Scenario: A database without FanGraphs

- **WHEN** `mlb report` runs on a database with no `raw.fangraphs_guts`
- **THEN** `gold.fangraphs_guts` is left untouched, no error is raised, and
  every other `gold` relation builds normally
- **AND** the FanGraphs health checks no-op rather than turn red

### Requirement: Health checks cover coverage and identity

`mlb doctor` SHALL report, for this capability, only when the relevant
`raw.fangraphs_*` source is present: that `gold.fangraphs_guts` has rows; that
`gold.fangraphs_guts` has a row for every season present in
`gold.batting_season` from 2003 onward; and `core.team` resolution coverage for
`gold.fangraphs_park_factors` (conformed rows versus every `season >= 2003` raw
row — a shortfall is an unresolved nickname, an over-count is alias fan-out). A
shortfall SHALL be actionable (which seasons / nicknames).

#### Scenario: A missing modern-season constant

- **WHEN** `gold.batting_season` has a 2019 season but `gold.fangraphs_guts`
  does not
- **THEN** `mlb doctor` flags 2019 as a missing FanGraphs constant row

### Requirement: FanGraphs projections are deferred to Beat 2

Conforming `raw.fangraphs_projection` into a `feat.*` relation SHALL NOT be
part of this capability's Beat 1. It is deferred so that a can-never-ship
(`local_research`) dependency is not baked into the walk-forward harness's
public contract before that interface exists, and so that the rights profile of
a `feat.*` relation that is rebuilt from code is a deliberate Beat 2 decision
rather than an inherited default.

#### Scenario: Projection conform is requested in Beat 1

- **WHEN** the Beat 1 change set is reviewed
- **THEN** it contains no `feat.fangraphs_projection` relation, no DuckDB
  feature file for it, and no `feat.py` wiring for it
