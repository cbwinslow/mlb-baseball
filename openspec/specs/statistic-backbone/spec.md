# statistic-backbone Specification

## Purpose
Defines the grain-complete classical statistic warehouse an outside sabermetric
researcher queries: which box-score relations exist, at what grain, computed
from what source, with what null and rights policy, and how each is validated
against published figures.

## Requirements

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

Coverage is the regular season. Game-grain rows are built from Retrosheet
events for 1910–2025 and from MLB's official per-game box score
(`raw.mlb_boxscore_batting` / `raw.mlb_boxscore_pitching`) for 2026 onward
(Retrosheet publishes no event file for the in-progress season). The two
builders SHALL each carry a `source` marker on the row and SHALL NOT both
write the same `(game, player, team)` key. The season / team / career
relations aggregate from the game grain and are source-agnostic.

#### Scenario: A traded player's season has per-team lines and one combined line

- **WHEN** a player appears for two teams in one season and the season relation is queried for that player and season
- **THEN** there is one line per team plus exactly one line flagged as the combined full-season total
- **AND** the combined line's counting stats equal the sum of the per-team lines

#### Scenario: A two-way player appears in both relations

- **WHEN** a player who both batted and pitched in a season is queried
- **THEN** the batting relation has that player's batting line and the pitching relation has that player's pitching line

#### Scenario: The current season is queryable

- **WHEN** the game-grain relations are queried for a completed regular-season game in 2026 or later
- **THEN** a box-score line is returned for every player who appeared, each marked with the `mlb_boxscore` source
- **AND** no game-grain row exists that was written by both the Retrosheet builder and the MLB builder

### Requirement: Statistics are computed from a primary game record, not from `core.play`

Batting and pitching lines SHALL be computed from a primary game record:
`raw.retrosheet_event` for 1910–2025, and MLB's official per-game box score
(`raw.mlb_boxscore_batting` / `raw.mlb_boxscore_pitching`) for 2026 onward.
The Retrosheet lines SHALL use the same event classification (at-bat,
batting-event, sacrifice, hit-code, RBI count) as the project's
already-tied-out team-level statistic builders. The lines SHALL NOT be
derived from `core.play`, which does not carry that event classification.

For 2026 onward the box score is MLB's own scorer-assigned line, so it is
authoritative for the counting stats; correctness is checked against an
independent reconstruction from `raw.mlb_playbyplay` events rather than
against Baseball-Reference (see the tie-out requirement).

#### Scenario: A backbone line matches the tied-out team builder's numbers

- **WHEN** a team-season total is derived by summing the backbone's player-season lines for that team
- **THEN** it matches the project's independently tied-out team wOBA/component builder for the same team and season, within the documented tolerance

#### Scenario: A 2026 box-score line matches a play-by-play reconstruction

- **WHEN** a 2026 player-game line is rebuilt from `raw.mlb_playbyplay` events and compared to the box-score-built row
- **THEN** every counting stat matches within the documented tolerance

### Requirement: Missing measurements are null with a stated reason, never guessed

A statistic the source data cannot support SHALL be left null with the reason
recorded in the spec, the table contract, or the column comment — never
imputed. In particular:

- earned-run average (`era`) and earned runs (`er`) are NOT produced by the
  Retrosheet-event relations for 1910–2025 (the event stream carries no
  earned-run / reconstructed-inning data); `ra9` is provided for every year.
  For 2026 onward the MLB box score carries scorer-assigned earned runs, so
  `er` and `era` are populated there. The resulting coverage cliff (`era`
  null through 2025, populated from 2026) SHALL be documented in the table
  contract;
- stolen bases and caught stealing are absent from the batting relations
  (deferred to a future baserunning relation), even where the 2026 source
  carries them;
- ground-into-double-play counts undercount before 1988 (sparse batted-ball
  coding upstream);
- a rate statistic SHALL be null when its denominator is zero.

#### Scenario: A rate stat is null on a zero denominator

- **WHEN** a player-season line has zero at-bats
- **THEN** batting average, on-base percentage, and slugging on that line are null, not zero and not an error

#### Scenario: ERA is not silently invented

- **WHEN** the pitching relations are queried for `era` on a 1910–2025 pitcher-season and on a 2026 pitcher-season
- **THEN** the 1910–2025 row's `era` is null because the event stream has no earned-run data, with `ra9` as the run-rate column
- **AND** the 2026 row's `era` is populated only because the MLB box score carries scorer-assigned earned runs, never reconstructed or guessed
- **AND** the coverage cliff is stated in the table contract

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
have a hand-calculated unit fixture for its rate formulas and an `mlb doctor`
check (row counts, null rates, join coverage against `core.game`).

A tie-out gate SHALL exist:

- **Baseball-Reference cited cases** (1910–2025 lineage) — a set of documented
  player-seasons whose every expected value was read from the exact
  Baseball-Reference page named in the case (never from memory). Counting
  stats match exactly; rate stats match to Baseball-Reference's displayed
  precision. The case shape SHALL support the game, season, team-season, and
  career grains so cases at any grain can be added.
- **Baseball-Reference bulk cross-check** (1910–2025 lineage) — for the
  seasons where `gold.player_season` (Baseball-Reference lineage) is
  trustworthy, the event-derived `gold.batting_season` / `gold.pitching_season`
  SHALL be compared against it field-by-field for every qualified
  player-season, and the gate SHALL fail if any field is outside a small
  documented tolerance on more than a small fraction of them.
- **Play-by-play cross-check** (2026 onward) — for a sample of 2026 games, the
  box-score-built game lines SHALL be compared field-by-field against a
  reconstruction from `raw.mlb_playbyplay` events, and the gate SHALL fail if
  a counting stat is outside a small documented tolerance on more than a small
  fraction of the sample. This stands in for the Baseball-Reference tie-out,
  which has no page for the in-progress season.

The Baseball-Reference bulk cross-check SHALL exclude the 2020 season
(COVID-shortened to 60 games — not a useful reference). It previously also
excluded 2021 onward, because `gold.player_season` folded in postseason games
for playoff teams; the `separate-postseason-stats` change fixed that at the
source, so 2021+ is a valid reference again and the gate runs through the last
completed season.

**Documented limitation.** Exact tie-out is not achievable at the career grain,
nor for seasons much before 2000: Retrosheet's event record and
Baseball-Reference's official record have each absorbed decades of independent
scoring corrections, so they differ by small amounts. This is a
source-of-record divergence, not a builder error. It is recorded in the
honest-limitations documentation.

The gate runs against a fully-built database, not in CI (CI has no real
Retrosheet events or MLB box scores).

#### Scenario: A rebuild produces identical rows

- **WHEN** a relation is built twice against the same source data
- **THEN** the two builds produce the same rows with the same values

#### Scenario: A real player-season ties out to Baseball-Reference

- **WHEN** the tie-out gate builds a documented modern player-season (e.g. a known MVP batting season, a known Cy Young pitching season) from real Retrosheet events
- **THEN** every counting stat matches the published Baseball-Reference line exactly and every rate stat matches to Baseball-Reference's display precision

#### Scenario: The event season tables agree with the Baseball-Reference-lineage table

- **WHEN** the bulk cross-check runs over the trustworthy seasons
- **THEN** for every checked field, the fraction of qualified player-seasons outside tolerance is below the gate's threshold
- **AND** the 2020 COVID-shortened season is not part of the comparison

#### Scenario: A 2026 game line agrees with a play-by-play reconstruction

- **WHEN** the play-by-play cross-check runs over its sample of 2026 games
- **THEN** for every checked counting stat, the fraction of player-game lines outside tolerance is below the gate's threshold

#### Scenario: A missing row fails a cited case

- **WHEN** a cited case names a player-season the built database does not contain
- **THEN** the gate exits non-zero and names the missing case

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
