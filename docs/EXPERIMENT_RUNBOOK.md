# Experiment runbook

The first experiment lab answers one narrow question: can a declared
probability model predict `home_win` from the point-in-time-safe
`game_base_v1` family? It is not a production forecast command.

`mlb features` remains the approved, audited feature build. The older
`mlb predict` path is compatibility-only: it rebuilds features, explicitly
derives sequential Elo, then writes its historical prediction relations. It is
not evidence of a fair experiment or valid backtest.

## Rehearsal sequence

Use `mlb_test` for all writes and verification.

```sh
DATABASE_URL=postgresql:///mlb_test uv run mlb experiment snapshot
DATABASE_URL=postgresql:///mlb_test uv run mlb experiment run \
  --snapshot <snapshot-id> --model logistic
DATABASE_URL=postgresql:///mlb_test uv run mlb experiment compare \
  --snapshot <snapshot-id>
DATABASE_URL=postgresql:///mlb_test uv run mlb audit
```

Run the same snapshot through `home_rate`, `log5`, `elo`, `logistic`,
`hist_gradient_boosting`, and `xgboost`. The report lists one result per
calendar fold; compare like-for-like folds, never a model's best isolated
season against another model's total.

## Why the split is chronological

Random train/test splits let later games teach a model about earlier ones. The
default development folds test 2016 through 2024 one season at a time using
only preceding seasons for training. 2025 is untouched final holdout; 2026 is
forward monitoring, not model selection.

**Why no purging/embargo (2026-08-13, independent research review):** financial
ML's walk-forward validation typically adds a *purge* (drop training rows whose
label window overlaps the test window) and an *embargo* (a buffer after the
cut) because a label like "5-day-forward return" can straddle a fold boundary
even when features are point-in-time-safe. This project's target (`home_win`)
is resolved same-day and every feature is already cutoff-safe, so there is no
overlapping-label window to purge — a season-boundary chronological split is
sufficient by construction. Recorded explicitly so a future reader doesn't have
to re-derive why this project's folds look simpler than the financial-ML
literature's, rather than wondering if it's a gap.

## Metrics and nulls

Log loss and Brier score judge probability quality. Accuracy is shown only as
a secondary thresholded summary. Calibration bins are retained, and slope or
intercept are omitted when the test fold is too small. First-game record rates
remain null: snapshots retain them, and the common Log5 comparison reports the
excluded rows instead of filling them silently. Python estimators use a
documented median-plus-missing-indicator preprocessing step.

## Add a model

1. Add one adapter in `mlb_baseball/model/experiment.py` that returns a finite
   probability in `[0, 1]`.
2. Use the shared snapshot, fold, scoring, and artifact path; do not add a
   model-specific training script.
3. Add unit/integration coverage proving its null behavior and same-row
   comparison.
4. Update the feature registry and research record if the model needs inputs
   beyond `game_base_v1`.

Scikit-learn and XGBoost are the supported initial libraries. MLflow and Optuna
remain deferred: no broad search or external tracking service is justified
before this small contract demonstrates a real need.

The typed experiment configuration is bound to its snapshot's `home_win`
target, `game_base_v1` version, source profile, calendar folds, seed,
calibration setting, parameters, and artifact location. Misspelled estimator
parameters, unsupported feature versions, malformed fold order, missing rows,
and time-overlapping folds fail clearly rather than silently producing a run.

## Current blockers before production experiments

- 2025 must remain untouched until a formal release gate.
- The lab has no model promotion, calibration fitting, broad hyperparameter
  search, market evaluation, or production prediction write path.
- Broader game/team/player/plate-appearance feature families require their own
  point-in-time contracts and tie-outs first.
