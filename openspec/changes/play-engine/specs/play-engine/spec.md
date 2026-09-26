## Purpose

Defines the plate-appearance engine: the calibrated, point-in-time probability
of each way a plate appearance can end, for a given batter, pitcher and game
situation, and the evidence required before the engine or any input to it is
accepted.

## ADDED Requirements

### Requirement: The plate-appearance dataset uses only information known before the plate appearance

The dataset SHALL contain one row per completed plate appearance, labelled with
exactly one outcome class. Every input on a row SHALL be knowable before that
plate appearance begins. Baserunning events that are not plate-appearance
outcomes (steals, pickoffs, wild pitches, balks and similar) SHALL NOT appear as
rows. Intentional walks SHALL be excluded from training and scoring because
they are a managerial choice, not a batter-versus-pitcher result, and the
exclusion SHALL be documented.

#### Scenario: A row is built for a plate appearance

- **WHEN** the dataset is built for a plate appearance in a given game
- **THEN** every batter and pitcher input reflects games before that game's
  calendar day only
- **AND** the row carries exactly one outcome class

#### Scenario: The leakage check is run on the dataset

- **WHEN** the existing point-in-time leakage checks are run against the dataset
- **THEN** no input available only after the plate appearance is present

#### Scenario: A player has no prior history

- **WHEN** a batter or pitcher has no prior plate appearances in the window
- **THEN** the input falls back to a documented shrunk prior, or is missing
- **AND** the missing value is never replaced by zero

### Requirement: Evaluation is chronological and the test seasons are never used for tuning

The engine SHALL be trained on 2015–2023 and scored on 2024–2025 walk-forward.
Feature choices and hyperparameters SHALL be selected using only seasons before
the test seasons. Tolerances used to judge the finish line SHALL be written down
before the test seasons are scored.

#### Scenario: A feature or setting is chosen

- **WHEN** a feature group or hyperparameter is selected
- **THEN** the selection used only 2015–2023 data
- **AND** the test seasons were not scored to make the choice

#### Scenario: Tolerances are recorded

- **WHEN** the test seasons are first scored
- **THEN** the calibration and simulation tolerances were already committed
  before that scoring

### Requirement: The engine is built as a ladder and each rung must earn its place

The engine SHALL be built as: a league-average baseline, then a ratings blend of
batter, pitcher, league and park, then a gradient-boosted multiclass model. A
rung SHALL be adopted only if it has a lower multiclass log loss than the rung
before it on the test seasons, measured with a paired comparison. A rung that
does not beat the one before SHALL be recorded as a negative result and not
adopted.

#### Scenario: A rung beats the previous rung

- **WHEN** the ratings blend has lower test-season log loss than the
  league-average baseline in the paired comparison
- **THEN** it is adopted as the current engine

#### Scenario: A rung does not beat the previous rung

- **WHEN** the gradient-boosted model does not beat the ratings blend
- **THEN** the result is recorded as a negative result with its numbers
- **AND** the ratings blend remains the shipped engine

### Requirement: The engine returns valid, calibrated probabilities

For any supported input, the engine SHALL return one probability per outcome
class, each between 0 and 1, summing to 1. Calibration SHALL be reported per
outcome class on the test seasons, and SHALL meet the documented tolerance for
the finish line.

#### Scenario: The engine is asked for a prediction

- **WHEN** the engine is given a batter, pitcher and situation
- **THEN** it returns a probability for every outcome class
- **AND** the probabilities sum to 1 within numerical tolerance

#### Scenario: Calibration is reported

- **WHEN** the test seasons are scored
- **THEN** a reliability result is reported for each outcome class alongside
  log loss

### Requirement: Every formula is tied to its published source and to real database values

Each formula the engine uses (the ratings blend, shrinkage, park adjustment and
any advanced input) SHALL be read from its primary source. It SHALL be reproduced
by a test that uses a worked example from that source, and checked against real
values from the project database. Where the primary source cannot be read (for
example a paywalled book), the entry SHALL say it was cited from a secondary
source and SHALL NOT claim a tie-out it did not perform.

#### Scenario: A formula is added

- **WHEN** a formula is added to the engine
- **THEN** its primary source is cited and a test reproduces a worked example
  from that source within a documented tolerance
- **AND** the same formula is checked against real values from the database

#### Scenario: The primary source cannot be read

- **WHEN** the primary source is unavailable
- **THEN** the citation is marked as secondary and no source tie-out is claimed

### Requirement: Each feature group is admitted separately, with a cited source and a measured effect

A feature group SHALL be added to the engine only after: its source is cited, it
passes the point-in-time leakage checks, and its effect on validation log loss
has been measured on its own. Every group tried, kept or rejected, SHALL be
recorded with the measured effect in a feature ledger. A rejected group SHALL NOT
be retried without new evidence.

#### Scenario: A feature group is added

- **WHEN** a feature group is proposed for the engine
- **THEN** its source citation and leakage-check result are recorded
- **AND** its measured effect is recorded in the feature ledger

#### Scenario: A feature group does not help

- **WHEN** a feature group shows no improvement beyond the noise of the paired
  comparison
- **THEN** it is recorded as rejected with its numbers and left out of the engine

### Requirement: A simulation built on the engine reproduces real totals

A base-out Markov chain and Monte Carlo simulation built on the engine SHALL
reproduce, on the test seasons, the real runs per game and home win rate within
the documented tolerance. Its result SHALL be reported next to `markov-v1`.

#### Scenario: The simulation is checked against real totals

- **WHEN** the simulation is run for the test seasons
- **THEN** simulated runs per game and home win rate are compared with the real
  values and reported against the documented tolerance

### Requirement: The engine ships with a model card and a feature ledger

The change SHALL commit a model card stating the training and test seasons, the
outcome classes, the measured log loss and calibration, known coverage limits,
and what the engine must not be used for. It SHALL also commit the feature
ledger.

#### Scenario: A researcher reads the model card

- **WHEN** a researcher opens the model card
- **THEN** it states the seasons, outcome classes, measured scores, limits and
  intended use
