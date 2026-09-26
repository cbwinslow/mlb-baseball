## Purpose

Governs the standalone, non-`gold`-materialized sabermetric calculator
engines under `mlb_baseball/model/` that a researcher or the CLI invokes
directly for a specific player/pitcher/team/season, so each one's formula
is traceable to a real published source and, where that source has a
data-driven form, computes from this project's own ingested data rather
than only from hand-typed inputs.

## ADDED Requirements

### Requirement: A calculator engine's formula is traceable to a real published source

Every standalone calculator engine in scope for this capability SHALL have
a `citation` in its `mlb_baseball/metrics/*.yaml` catalog entry that names a
real, independently verifiable published source (a paper, book, or a
data provider's own documented methodology) for each distinct claim the
engine makes. A constant, threshold, or sub-formula with no such source
SHALL NOT be presented as though it came from the cited source.

#### Scenario: A citation covers only what it actually supports

- **WHEN** a calculator engine combines a cited formula with an
  additional uncited constant, threshold, or heuristic
- **THEN** the catalog entry's `citation` and the engine's own
  documentation distinguish the cited part from the uncited part, rather
  than attributing the whole output to the cited source

### Requirement: Arm slot classification uses Statcast's own published arm-angle measurement

`arm_slot_engine` SHALL classify a pitcher's arm slot from Statcast's own
published per-pitch arm-angle measurement for that pitcher over a caller-
specified date range, when that measurement exists for the pitcher/range,
rather than deriving an angle from an uncited anatomical assumption.

#### Scenario: A pitcher with Statcast arm-angle coverage gets a real classification

- **WHEN** a caller requests an arm-slot classification for a pitcher and
  date range where Statcast arm-angle data exists
- **THEN** the returned angle and tier are derived from that real,
  per-pitch measurement (e.g. its mean or mode over the range), not from
  an estimated shoulder height

#### Scenario: No silent fabrication when Statcast arm-angle coverage is absent

- **WHEN** a caller requests an arm-slot classification for a pitcher/date
  range where Statcast arm-angle data does not exist (e.g. before
  Statcast began publishing it)
- **THEN** the engine reports that no real measurement is available rather
  than silently substituting an estimated or default angle

### Requirement: BABIP luck scanning compares a real actual outcome to a real expected-outcome model

`babip_luck_scanner` SHALL compute a batter's actual BABIP and an expected
BABIP for a caller-specified batter and date range from this project's own
ingested batted-ball data, using a real, cited expected-outcome model,
rather than an uncited hand-derived linear formula. The hand-typed
what-if mode MAY remain available, but SHALL be clearly and separately
labeled as illustrative/scouting input, not as a real player's data.

#### Scenario: A real batter's real BABIP luck is computed from real data

- **WHEN** a caller requests a real-data BABIP luck evaluation for a
  batter and date range with ingested batted-ball coverage
- **THEN** both the actual BABIP and the expected BABIP are computed from
  that batter's own real balls in play, and the regression tier follows
  from their real difference

#### Scenario: Hand-typed input is never presented as a real player's data

- **WHEN** a caller uses the hand-typed what-if mode
- **THEN** the output is labeled as a hypothetical/scouting input
  evaluation, not attributed to any specific real player's actual
  performance

### Requirement: Pitch tunneling evaluation implements the real published methodology

`pitch_tunneling_engine` SHALL evaluate a caller-specified pitcher's two
real pitch types, over a caller-specified date range, using real release
and trajectory data from this project's own ingested pitch-tracking data
and the published pitch-tunnels methodology it cites, rather than an
uncited approximation. The hand-typed what-if mode MAY remain available
under the same labeling requirement as BABIP luck scanning above.

#### Scenario: A real pitcher's two real pitch types are evaluated for tunneling

- **WHEN** a caller requests a real-data tunneling evaluation for a
  pitcher's two pitch types over a date range with ingested
  pitch-tracking coverage
- **THEN** release distance, decision-point separation, and plate-break
  separation are computed from that pitcher's own real pitches, using the
  cited methodology's definitions

### Requirement: Season simulation team strength reflects each team's real performance

`season_monte_carlo_simulation`, as invoked by the `mlb season-sim` CLI
command, SHALL derive each team's simulated true-talent win percentage
from that team's own real runs-scored and runs-allowed as of the
simulation's point-in-time cutoff, rather than assigning every team an
identical placeholder value.

#### Scenario: Teams with different real performance get different simulated talent

- **WHEN** `mlb season-sim` is run for a season where teams have a real,
  differing games-played history as of the cutoff date
- **THEN** the simulated true-talent win percentages fed into the Monte
  Carlo run differ across teams according to their real run-scoring and
  run-prevention performance

#### Scenario: No future information leaks into a team's simulated talent

- **WHEN** a team-strength estimate is computed for a simulation with a
  point-in-time cutoff
- **THEN** only games completed strictly before that cutoff contribute to
  the estimate

#### Scenario: An honest fallback when a team has no prior real games

- **WHEN** a team has no completed games before the simulation's cutoff
  (e.g. very early in a season)
- **THEN** the simulation uses a documented, clearly-labeled fallback
  (such as a league-average win percentage) for that team rather than
  fabricating a differentiated value it has no evidence for
