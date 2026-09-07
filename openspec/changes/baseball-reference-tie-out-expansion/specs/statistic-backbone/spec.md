## MODIFIED Requirements

### Requirement: Each relation is deterministic and validated against a published figure

Rebuilding a relation over unchanged source data SHALL be idempotent
(truncate-and-replace, transactional; identical rows). Each relation SHALL
have a hand-calculated unit fixture for its rate formulas and an `mlb doctor`
check (row counts, null rates, join coverage against `core.game`).

A Baseball-Reference tie-out gate SHALL exist with two parts:

- **Cited cases** — a set of documented player-seasons whose every expected
  value was read from the exact Baseball-Reference page named in the case
  (never from memory). Counting stats match exactly; rate stats match to
  Baseball-Reference's displayed precision. The case shape SHALL support the
  game, season, team-season, and career grains so cases at any grain can be
  added.
- **Bulk cross-check** — for the seasons where `gold.player_season`
  (Baseball-Reference lineage) is trustworthy, the event-derived
  `gold.batting_season` / `gold.pitching_season` SHALL be compared against it
  field-by-field for every qualified player-season, and the gate SHALL fail if
  any field is outside a small documented tolerance on more than a small
  fraction of them.

The bulk cross-check SHALL exclude seasons from 2020 onward: `gold.player_season`
from 2021 folds in postseason games (an upstream Baseball-Reference / pybaseball
date-range issue, tracked and fixed separately), so it is not a valid reference
for those years.

**Documented limitation.** Exact tie-out is not achievable at the career grain,
nor for seasons much before 2000: Retrosheet's event record and
Baseball-Reference's official record have each absorbed decades of independent
scoring corrections, so they differ by small amounts. This is a
source-of-record divergence, not a builder error. It is recorded in the
honest-limitations documentation.

The gate runs against a fully-built database, not in CI (CI has no real
Retrosheet events).

#### Scenario: A rebuild produces identical rows

- **WHEN** a relation is built twice against the same source data
- **THEN** the two builds produce the same rows with the same values

#### Scenario: A real player-season ties out to Baseball-Reference

- **WHEN** the tie-out gate builds a documented modern player-season (e.g. a known MVP batting season, a known Cy Young pitching season) from real Retrosheet events
- **THEN** every counting stat matches the published Baseball-Reference line exactly and every rate stat matches to Baseball-Reference's display precision

#### Scenario: The event season tables agree with the Baseball-Reference-lineage table

- **WHEN** the bulk cross-check runs over the trustworthy seasons
- **THEN** for every checked field, the fraction of qualified player-seasons outside tolerance is below the gate's threshold
- **AND** seasons from 2020 onward are not part of the comparison

#### Scenario: A missing row fails a cited case

- **WHEN** a cited case names a player-season the built database does not contain
- **THEN** the gate exits non-zero and names the missing case
