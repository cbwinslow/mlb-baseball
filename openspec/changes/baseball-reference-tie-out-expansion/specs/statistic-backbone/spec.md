## MODIFIED Requirements

### Requirement: Each relation is deterministic and validated against a published figure

Rebuilding a relation over unchanged source data SHALL be idempotent
(truncate-and-replace, transactional; identical rows). Each relation SHALL
have a hand-calculated unit fixture for its rate formulas and an `mlb doctor`
check (row counts, null rates, join coverage against `core.game`).

A Baseball-Reference tie-out gate SHALL cover **every backbone grain** —
game, season, team-season, and career, for both batting and pitching. Each
tie-out case builds the relation from real Retrosheet events and asserts the
line against a cited Baseball-Reference page: counting stats match exactly,
rate stats match to Baseball-Reference's displayed precision. A case whose row
is absent SHALL fail the gate (never silently pass).

The gate's cases SHALL fall in the range 1950–present, where Retrosheet event
data is contemporaneous and complete; every case in that range is expected to
match exactly. Pre-1950 seasons (which include deduced / reconstructed
play-by-play) are explicitly out of the gate's scope, recorded as follow-up.

The gate runs against a fully-built database, not in CI (CI has no real
Retrosheet events).

#### Scenario: A rebuild produces identical rows

- **WHEN** a relation is built twice against the same source data
- **THEN** the two builds produce the same rows with the same values

#### Scenario: A real player-season ties out to Baseball-Reference

- **WHEN** the tie-out gate builds a documented player-season (e.g. a known MVP batting season, a known Cy Young pitching season) from real Retrosheet events
- **THEN** every counting stat matches the published Baseball-Reference line exactly and every rate stat matches to Baseball-Reference's display precision

#### Scenario: Every grain ties out to Baseball-Reference

- **WHEN** the tie-out gate runs against a fully-built database
- **THEN** it checks at least one batting and one pitching case at each of the game, season, team-season, and career grains
- **AND** each case's counting stats match the cited Baseball-Reference line exactly and each rate stat matches to Baseball-Reference's display precision

#### Scenario: A traded player's combined season ties out

- **WHEN** the gate checks a player who changed teams mid-season
- **THEN** the `is_combined` full-season line matches the player's Baseball-Reference full-season row (not either single-team stint)

#### Scenario: A missing row fails the gate

- **WHEN** a tie-out case names a player-season the built database does not contain
- **THEN** the gate exits non-zero and names the missing case
