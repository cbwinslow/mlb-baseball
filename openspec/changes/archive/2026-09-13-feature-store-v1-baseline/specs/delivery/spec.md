## ADDED Requirements

### Requirement: The public distribution includes one reference baseline model and its model card

The installable package (`mlb-research`) SHALL include one reference baseline
predictive model (Elo v2) and a reproducible model card reporting its
evaluation, satisfying the "an analyst reproduces the model card by running
the shipped harness against their own build" clause the backtest-harness
requirement names.

The reference model SHALL:

- **fit and predict through the shipped harness.** Elo v2 SHALL be evaluated
  by calling the package's own walk-forward backtest harness as an ordinary
  `fit_fn` / `predict_fn` pair — no separate evaluation path.
- **need no database and no paid or restricted data source.** Elo v2 and its
  model card SHALL run against the package's own point-in-time feature store
  output alone. Neither SHALL require a database connection, a market-odds
  feed, or any source not already part of the public distribution.
- **report probability quality for two configurations, matched.** The model
  card SHALL report log loss, Brier score, and calibration for Elo v2 with
  its starter-quality adjustment enabled, and separately with it disabled (a
  home-field-only baseline), and SHALL report a matched-sample comparison of
  the two over identical evaluation games.
- **treat a missing input as missing, not average.** Where a per-game input
  the starter adjustment depends on is unavailable, Elo v2 SHALL apply no
  adjustment for that game rather than substituting a league-average or other
  fabricated value.
- **be reproducible from the shipped package alone.** Re-running the model
  card against the same public feature-store build SHALL reproduce its
  reported numbers within the harness's documented tolerance, with no
  project-operated service and no pre-trained artifact required.

This requirement does not require Elo v2 to use a probable starting pitcher,
compare against betting-market odds, or compare against any other model
(including the project's own production Elo implementation) — those remain
explicitly out of scope for this requirement and may be added by a later
requirement without changing this one.

#### Scenario: The model card runs from the public package alone

- **WHEN** an analyst installs `mlb-research`, builds the feature store locally, and runs the model card
- **THEN** it completes and reports Elo v2's log loss, Brier score, and calibration, both with and without the starter adjustment
- **AND** no database connection, market-data fetch, or non-public dependency is required

#### Scenario: The two configurations are compared on the same games

- **WHEN** the model card backtests Elo v2 with the starter adjustment on and, separately, with it off
- **THEN** the reported comparison between the two covers exactly the evaluation games both configurations scored
- **AND** the count of those games is reported alongside the comparison

#### Scenario: A missing starter input produces no adjustment, not a guess

- **WHEN** a game's starter-quality input is unavailable at evaluation time
- **THEN** Elo v2 predicts that game using the unadjusted team rating
- **AND** no league-average or other substitute value is used in its place

#### Scenario: Re-running the model card reproduces its numbers

- **WHEN** an analyst re-runs the model card against an unchanged local feature-store build
- **THEN** the reported log loss, Brier score, and calibration match the previous run within the harness's documented tolerance
