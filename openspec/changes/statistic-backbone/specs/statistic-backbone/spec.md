## Purpose

Defines the grain-complete classical statistic warehouse an outside sabermetric
researcher queries: which box-score relations exist, at what grain, computed
from what source, with what null and rights policy, and how each is validated
against published figures.

## ADDED Requirements

### Requirement: A statistic relation exists at every grain of the ladder

The system SHALL provide a classical batting statistic relation and a classical
pitching statistic relation at each of these grains:

- `(batter | pitcher, game)` — one box-score line per player per game;
- `(player, season, team)` — one stint line per team, plus exactly one
  combined full-season line per `(player, season)` (the combined line's team
  key is null; a one-team player's combined line equals the stint);
- `(team, season)`;
- `(player)` career.

A player who both bats and pitches SHALL appear in both the batting and the
pitching relation at each grain. A player who appears for two teams in one
game SHALL get two game-grain rows (team is part of the key), not a collision.

Coverage is the regular season. The Retrosheet-event builder covers 1910–2025.
A 2026-onward builder over `raw.mlb_playbyplay` is planned follow-up work; when
it lands it SHALL meet the same source-fidelity and null-policy requirements
below.

#### Scenario: A traded player's season has per-team lines and one combined line

- **WHEN** a player appears for two teams in one season and the season relation is queried for that player and season
- **THEN** there is one line per team plus exactly one line flagged as the combined full-season total
- **AND** the combined line's counting stats equal the sum of the per-team lines

#### Scenario: A two-way player appears in both relations

- **WHEN** a player who both batted and pitched in a season is queried
- **THEN** the batting relation has that player's batting line and the pitching relation has that player's pitching line

### Requirement: Statistics are computed from Retrosheet events, not from `core.play`

Batting and pitching lines SHALL be computed from `raw.retrosheet_event`
(1910–2025; and from `raw.mlb_playbyplay` for 2026 onward once that builder
lands), using the same event classification (at-bat, batting-event, sacrifice,
hit-code, RBI count) as the project's already-tied-out team-level statistic
builders. The lines SHALL NOT be derived from `core.play`, which does not carry
that event classification.

#### Scenario: A backbone line matches the tied-out team builder's numbers

- **WHEN** a team-season total is derived by summing the backbone's player-season lines for that team
- **THEN** it matches the project's independently tied-out team wOBA/component builder for the same team and season, within the documented tolerance

### Requirement: Missing measurements are null with a stated reason, never guessed

A statistic the source data cannot support SHALL be left null with the reason
recorded in the spec, the table contract, or the column comment — never
imputed. In particular:

- earned-run average (`era`) is NOT produced by the event-derived relations
  (no earned-run / reconstructed-inning data); the honest event rate `ra9` is
  provided instead;
- stolen bases and caught stealing are absent from the batting relations
  (deferred to a future baserunning relation);
- ground-into-double-play counts undercount before 1988 (sparse batted-ball
  coding upstream);
- a rate statistic SHALL be null when its denominator is zero.

#### Scenario: A rate stat is null on a zero denominator

- **WHEN** a player-season line has zero at-bats
- **THEN** batting average, on-base percentage, and slugging on that line are null, not zero and not an error

#### Scenario: ERA is not silently invented

- **WHEN** the pitching relations are queried for an earned-run average column
- **THEN** none is present; `ra9` is the run-rate column, and the absence of `era` is documented

### Requirement: Roll-ups flow one direction; rates are recomputed from summed components

Season lines SHALL be aggregated from the game-grain relation; career lines
SHALL be aggregated from the season relation's combined full-season rows (so a
traded season counts once). A relation SHALL NOT be built from a sibling
relation at the same grain. Every rate statistic on a roll-up SHALL be
recomputed from that grain's summed numerator and denominator, not averaged
from a finer grain's rates.

#### Scenario: Career batting average is recomputed, not averaged

- **WHEN** a player's career line is built from seasons with different at-bat totals
- **THEN** the career batting average equals total career hits divided by total career at-bats, not the mean of the season averages

### Requirement: Each relation is deterministic and validated against a published figure

Rebuilding a relation over unchanged source data SHALL be idempotent
(truncate-and-replace, transactional; identical rows). Each relation SHALL
have: a hand-calculated unit fixture for its rate formulas; an integration
tie-out test that builds one real player-season from real events and asserts
the line matches the published Baseball-Reference figure within a stated
tolerance (skipped with a visible marker if the fixture data is absent, never
silently passing); and an `mlb doctor` check (row counts, null rates, join
coverage against `core.game`).

#### Scenario: A rebuild produces identical rows

- **WHEN** a relation is built twice against the same source data
- **THEN** the two builds produce the same rows with the same values

#### Scenario: A real player-season ties out to Baseball-Reference

- **WHEN** the tie-out test builds a documented player-season (e.g. a known MVP batting season, a known Cy Young pitching season) from real Retrosheet events
- **THEN** every counting stat matches the published Baseball-Reference line exactly and every rate stat matches to Baseball-Reference's display precision

### Requirement: Backbone relations are `local_research`, not `public_safe`

Every backbone relation SHALL be registered in the `mlb export` allow-list
with the `local_research` profile, because its builder joins the conformed
`core` dimensions (which mix non-Retrosheet sources) for surrogate keys, and
`public_safe` admits Retrosheet-only lineage. A `public_safe` variant keyed by
Retrosheet identifiers is permitted future work and SHALL NOT be assumed to
exist.

#### Scenario: A backbone relation is excluded from the public-safe bundle

- **WHEN** the public-safe export preset runs
- **THEN** the backbone relations are not included, and the exclusion reason (core-dimension lineage) is recorded

### Requirement: The two season lines are parallel sources, not one writer

`gold.player_season` / `gold.team_season` (Baseball-Reference / Lahman
sourced, 2008 onward, carrying `era` and other official-source fields) and the
event-derived `gold.batting_season` / `gold.pitching_season` (1910 onward,
team-aware, `ra9` not `era`) SHALL be documented as distinct season lines
serving distinct purposes. Neither SHALL be defined as a view over, or a
second writer into, the other.

#### Scenario: Both season lines are queryable and independently sourced

- **WHEN** a researcher queries a 2015 player-season from `gold.player_season` and from `gold.batting_season`
- **THEN** both return a line, each labelled with its source, and the docs explain that one is the Baseball-Reference official line and the other is event-computed
