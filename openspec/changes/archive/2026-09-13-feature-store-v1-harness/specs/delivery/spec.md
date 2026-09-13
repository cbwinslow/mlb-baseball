## ADDED Requirements

### Requirement: The shipped backtest harness is model-agnostic and dependency-light

The public distribution SHALL include a walk-forward backtest harness in the
installable package (`mlb-research`), usable by an analyst against their own
build with no database server and no model-training library installed.

The harness SHALL:

- **fit no model itself.** Model fitting and prediction SHALL be supplied by the
  caller as a `fit_fn` / `predict_fn` callback pair. The package SHALL NOT
  import `scikit-learn`, `xgboost`, `PyMC`, or any other model-training library
  at module load or during a backtest run.
- **split only by time.** Every fold's training rows SHALL fall strictly before
  its evaluation rows on the caller-named cutoff column. A random or shuffled
  split SHALL NOT be expressible through the harness API.
- **never select on the evaluation period.** The harness SHALL expose no
  parameter or hook that fits, tunes, or chooses features or hyperparameters
  using rows from a fold's own evaluation period.
- **take a plain table in.** Input SHALL be a single in-memory tabular frame
  (one row per evaluation unit, a cutoff-timestamp column, feature columns, a
  label column). A row missing a required input SHALL be reported as excluded,
  never imputed or filled.
- **report probability quality.** For a classification target the harness SHALL
  report log loss, Brier score, and a binned reliability (calibration) table
  with an intercept and slope; for a regression target, mean absolute error,
  root mean squared error, and a residual-decile calibration table. Accuracy MAY
  be reported but SHALL NOT be the only score. Interval estimates (e.g.
  bootstrap confidence intervals) SHALL be reproducible from a recorded seed.
- **support a matched-sample comparison.** The harness SHALL provide a paired
  comparison of two models' predictions computed over exactly the evaluation
  units both models scored, so a baseline and a candidate are compared on the
  same games.
- **return a serializable result.** A backtest run SHALL return per-fold and
  aggregate metrics, the fold plan, the included/excluded row counts, and the
  seed, in a form that serializes to JSON for a model card.

This requirement names the guarantee, not an implementation. It exists so that
the "an analyst reproduces the model card by running the shipped harness against
their own build" clause of *The public distribution includes one reference
baseline model* is actually satisfiable.

#### Scenario: The harness runs with no model-training library installed

- **WHEN** an analyst imports and runs the harness in an environment where `scikit-learn` and `xgboost` are not installed, passing their own `fit_fn` / `predict_fn`
- **THEN** the backtest completes and returns per-fold and aggregate probability-quality metrics
- **AND** no import error is raised for a model-training library

#### Scenario: Folds are strictly time-ordered

- **WHEN** a backtest is configured over several evaluation periods
- **THEN** for every fold, every training row's cutoff timestamp is strictly earlier than every evaluation row's cutoff timestamp
- **AND** the API offers no option to produce a random or shuffled split

#### Scenario: A missing required input is excluded, not imputed

- **WHEN** the input frame contains a row whose required feature value is null
- **THEN** that row is omitted from both training and evaluation and counted in the result's excluded-row count
- **AND** no substitute or filled value is used for it

#### Scenario: Two models are compared on the same games

- **WHEN** an analyst runs the paired comparison of a baseline and a candidate model whose predictions cover overlapping but not identical sets of games
- **THEN** the comparison metrics are computed only over the games both models scored
- **AND** the count of those common games is reported

#### Scenario: The reference model card is reproducible from the shipped harness

- **WHEN** an analyst runs the shipped harness against their own build for the reference baseline's stated chronological hold-out
- **THEN** the calibration, log loss, and Brier score match the published model card within its documented tolerance
- **AND** the run required no project-operated service and no pre-trained artifact
