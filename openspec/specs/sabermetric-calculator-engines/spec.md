# sabermetric-calculator-engines Specification

## Purpose

Governs standalone, non-`gold`-materialized sabermetric calculator engines
that researchers or the CLI invoke for a specific player, pitcher, team, or
season. Their formulas must be traceable to published sources and, when a
source has a data-driven form, run from this project's ingested data rather
than only hand-typed inputs.

## Requirements

### Requirement: A calculator engine's formula is traceable to a real published source

Every standalone calculator engine in scope for this capability SHALL have
a `citation` in its `mlb_baseball/metrics/*.yaml` catalog entry that names a
real, independently verifiable published source (a paper, book, or a data
provider's documented methodology) for each distinct claim the engine makes.
A constant, threshold, or sub-formula with no such source SHALL NOT be
presented as though it came from the cited source.

#### Scenario: A citation covers only what it actually supports

- **WHEN** a calculator engine combines a cited formula with an additional
  uncited constant, threshold, or heuristic
- **THEN** the catalog entry's `citation` and the engine's documentation
  distinguish the cited part from the uncited part rather than attributing
  the whole output to the cited source

### Requirement: Arm slot classification uses Statcast's own published arm-angle measurement

`arm_slot_engine` SHALL classify a pitcher's arm slot from Statcast's own
published per-pitch arm-angle measurement for that pitcher over a
caller-specified date range when that measurement exists, rather than deriving
an angle from an uncited anatomical assumption.

#### Scenario: A pitcher with Statcast arm-angle coverage gets a real classification

- **WHEN** a caller requests an arm-slot classification for a pitcher and date
  range where Statcast arm-angle data exists
- **THEN** the returned angle and tier are derived from that real per-pitch
  measurement, not from an estimated shoulder height

#### Scenario: No silent fabrication when Statcast arm-angle coverage is absent

- **WHEN** a caller requests an arm-slot classification for a pitcher/date
  range where Statcast arm-angle data does not exist
- **THEN** the engine reports that no real measurement is available rather than
  silently substituting an estimated or default angle

### Requirement: BABIP luck scanning compares a real actual outcome to a real expected-outcome model

`babip_luck_scanner` SHALL compute a batter's actual BABIP and expected BABIP
for a caller-specified batter and date range from this project's ingested
batted-ball data, using a real, cited expected-outcome model rather than an
uncited hand-derived linear formula. The hand-typed what-if mode MAY remain
available but SHALL be clearly and separately labeled as illustrative input,
not as a real player's data.

#### Scenario: A real batter's real BABIP luck is computed from real data

- **WHEN** a caller requests a real-data BABIP luck evaluation for a batter and
  date range with ingested batted-ball coverage
- **THEN** actual BABIP and expected BABIP are computed from that batter's real
  balls in play, and the regression tier follows from their real difference

#### Scenario: Hand-typed input is never presented as a real player's data

- **WHEN** a caller uses the hand-typed what-if mode
- **THEN** the output is labeled as a hypothetical/scouting-input evaluation,
  not attributed to a specific real player's performance

### Requirement: Pitch tunneling evaluation implements the real published methodology

`pitch_tunneling_engine` SHALL evaluate a caller-specified pitcher's two real
pitch types over a caller-specified date range using real release and
trajectory data from this project's ingested pitch-tracking data and the
published methodology it cites, rather than an uncited approximation. The
hand-typed what-if mode MAY remain available under the same labeling
requirement as BABIP luck scanning.

#### Scenario: A real pitcher's two real pitch types are evaluated for tunneling

- **WHEN** a caller requests a real-data tunneling evaluation for a pitcher's
  two pitch types over a date range with ingested pitch-tracking coverage
- **THEN** release distance, decision-point separation, and plate-break
  separation are computed from that pitcher's real pitches using the cited
  methodology's definitions

### Requirement: Season simulation team strength reflects each team's real performance

`season_monte_carlo_simulation`, as invoked by `mlb season-sim`, SHALL derive
each team's simulated true-talent win percentage from that team's real
runs-scored and runs-allowed as of the simulation's point-in-time cutoff,
rather than assigning every team an identical placeholder value.

#### Scenario: Teams with different real performance get different simulated talent

- **WHEN** `mlb season-sim` runs for a season where teams have differing
  completed-game histories as of the cutoff date
- **THEN** the simulated true-talent win percentages differ according to real
  run-scoring and run-prevention performance

#### Scenario: No future information leaks into a team's simulated talent

- **WHEN** a team-strength estimate is computed for a simulation with a
  point-in-time cutoff
- **THEN** only games completed strictly before that cutoff contribute to the
  estimate

#### Scenario: An honest fallback when a team has no prior real games

- **WHEN** a team has no completed games before the simulation cutoff
- **THEN** the simulation uses a documented, clearly labeled fallback rather
  than fabricating a differentiated value without evidence
