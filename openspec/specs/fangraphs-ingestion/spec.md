# fangraphs-ingestion Specification

## Purpose
Defines how FanGraphs' public bulk data enters the warehouse: which
`raw.fangraphs_*` relations exist, from which FanGraphs product each is built,
their refresh and history-retention semantics, their idempotency guarantees,
the data-rights profile that gates them, and the health signals a maintainer
watches. It is a raw-ingestion contract only — conforming FanGraphs identities
or metrics into `core`/`gold` is out of scope.

## Requirements

### Requirement: A FanGraphs connector lands source-faithful bulk data

The system SHALL provide a `fangraphs` source connector, registered alongside
the other connectors, that acquires FanGraphs' public bulk data and lands it in
`raw.fangraphs_*` relations. It SHALL reach FanGraphs through a client that
FanGraphs' Cloudflare layer does not block, SHALL NOT use the `pybaseball`
FanGraphs path (confirmed permanently 403), and SHALL require no FanGraphs
account or credentials.

Raw relations SHALL preserve FanGraphs' own column names and native value types
(numbers stay numbers), including the full wide pitching leaderboard with its
Stuff+ and PitchingBot column families. Genuine source inconsistencies SHALL
NOT be silently normalised at the raw layer.

The connector SHALL expose `bootstrap()`, `update()`, and `health_check()`.

#### Scenario: The connector is a registered source

- **WHEN** the list of ingestion sources is enumerated (CLI, `mlb doctor`, bootstrap/update orchestration)
- **THEN** `fangraphs` is present and its `bootstrap()` / `update()` are runnable individually and as part of a full run

#### Scenario: Cloudflare withdraws the access exemption

- **WHEN** FanGraphs starts returning an access-denied response to the connector's client
- **THEN** the run fails with an error that names the cause (the access path is blocked), the affected relations keep their last good data, and `health_check()` reports the failed run
- **AND** the connector does not silently retry into an unbounded loop

### Requirement: Season leaderboards cover all available history and replace by season

`raw.fangraphs_batting`, `raw.fangraphs_pitching`, and `raw.fangraphs_fielding`
SHALL each hold one row per player per season, for every season FanGraphs
publishes that board. `bootstrap()` SHALL load the full history one season at a
time; a single season's failure SHALL NOT discard already-committed seasons.
`update()` SHALL reload the current season only. Re-running either SHALL leave
row counts and grain unchanged (per-season scoped replace).

Era-dependent sparsity SHALL be preserved as genuine nulls, not zero-filled.

#### Scenario: Bootstrap is interrupted and resumed

- **WHEN** a bootstrap run fails partway through the season range and is re-run
- **THEN** already-loaded seasons are not re-fetched or duplicated, and the run continues from where it stopped

#### Scenario: Update is idempotent

- **WHEN** `update()` runs twice in succession
- **THEN** `raw.fangraphs_batting` / `_pitching` / `_fielding` for the current season have the same rows after the second run as after the first

### Requirement: Slowly-changing reference boards are whole-table or per-season replaces

`raw.fangraphs_guts` (the Guts! wOBA/FIP constants) SHALL be loaded as a single
whole-table replace covering all seasons FanGraphs returns.
`raw.fangraphs_park_factors`, `raw.fangraphs_park_factors_handedness`, and
`raw.fangraphs_prospects` SHALL be per-season scoped replaces. All SHALL be
idempotent under re-run.

#### Scenario: Guts constants reload

- **WHEN** `update()` runs after FanGraphs revises the current season's wOBA scale
- **THEN** `raw.fangraphs_guts` reflects the revised current-season row and every historical row is unchanged

### Requirement: Projections are retained as a dated, de-duplicated snapshot history

`raw.fangraphs_projection` SHALL store every preseason and rest-of-season
projection system the connector's client exposes. Each row SHALL carry the
projection system, the stat group, the player identifier, the capture date, and
whether it is a preseason or rest-of-season projection. The relation SHALL be
append-only: an `update()` run SHALL add a new snapshot for a key only when the
projected values differ from that key's most recent stored snapshot, so an
unchanged projection does not accumulate duplicate rows.

A researcher SHALL be able to reconstruct, for any player and system, how that
projection changed over time from this one relation.

#### Scenario: Projection moves between runs

- **WHEN** a player's Steamer rest-of-season projection changes and `update()` runs
- **THEN** a new dated snapshot row is appended for that player/system, and the prior snapshot rows remain

#### Scenario: Projection unchanged between runs

- **WHEN** `update()` runs twice on the same day with no upstream projection change
- **THEN** no second snapshot row is written for the unchanged keys

### Requirement: A curated set of split leaderboards is landed

`raw.fangraphs_split_batting` and `raw.fangraphs_split_pitching` SHALL hold a
curated set of the most commonly used league-wide split leaderboards (at
minimum: versus left-handed pitching, versus right-handed pitching, home,
road, and by calendar month), one row per player per season per split, per
season scoped replace. The full FanGraphs split-code catalogue and any
per-player-only FanGraphs endpoint are out of scope for this capability;
their absence SHALL be documented, not treated as a bug.

#### Scenario: A platoon split is queryable

- **WHEN** `raw.fangraphs_split_batting` is queried for a season and the "vs RHP" split
- **THEN** there is one row per qualifying batter for that season and split

### Requirement: FanGraphs data is rights-gated to local research

FanGraphs SHALL be recorded in the source-rights register at the
`local_research` profile with no evidence for public display, redistribution,
or model-training use. The ingest guard SHALL block the `fangraphs` connector
under any non-`local_research` profile before it makes a network request, and
no `public_safe` export relation SHALL be backed by a `raw.fangraphs_*` table
until the rights register is updated with recorded evidence.

#### Scenario: A restricted profile blocks the connector

- **WHEN** `mlb ingest fangraphs` is invoked under the `public_safe` profile
- **THEN** it exits with a rights error citing the source-rights document and makes no request to FanGraphs

### Requirement: A cron refresh keeps the data current and captures projection movement

The `fangraphs` connector SHALL be refreshed by the scheduled pipeline that
runs the other connectors' `update()`. Because projections change more than
once per day, a dedicated scheduled job SHALL additionally run the connector's
`update()` on a sub-daily cadence to capture projection snapshots as they
move. Scheduled runs SHALL be single-flighted (an overlapping run is skipped,
not stacked) and SHALL append to a log a maintainer can inspect.
`health_check()` SHALL detect when the scheduled refresh has silently stopped.

#### Scenario: Overlapping scheduled runs

- **WHEN** a scheduled `fangraphs` update is still running and the next scheduled tick fires
- **THEN** the second invocation detects the in-progress run and exits without starting a duplicate

#### Scenario: Refresh has stopped

- **WHEN** the scheduled refresh has not completed successfully for longer than its expected interval
- **THEN** `health_check()` (and `mlb doctor`) report a stale/failed FanGraphs refresh with enough detail to act on
