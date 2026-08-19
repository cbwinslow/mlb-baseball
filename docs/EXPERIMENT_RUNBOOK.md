# Experiment runbook

The experiment lab answers narrow questions on declared targets (`home_win`
classification, `run_differential` regression) from the point-in-time-safe
`game_base_v1` family. It is not a production forecast command.

`mlb features` remains the approved, audited feature build. The older
`mlb predict` path is compatibility-only: it rebuilds features, explicitly
derives sequential Elo, then writes its historical prediction relations. It is
not evidence of a fair experiment or valid backtest.

## Rehearsal sequence

Use `mlb_test` for all writes and verification.

```sh
# Classification (home_win)
DATABASE_URL=postgresql:///mlb_test uv run mlb experiment snapshot --target home_win
DATABASE_URL=postgresql:///mlb_test uv run mlb experiment run \
  --snapshot <snapshot-id> --target home_win --model logistic
DATABASE_URL=postgresql:///mlb_test uv run mlb experiment compare \
  --snapshot <snapshot-id>

# Regression (run_differential)
DATABASE_URL=postgresql:///mlb_test uv run mlb experiment snapshot --target run_differential
DATABASE_URL=postgresql:///mlb_test uv run mlb experiment run \
  --snapshot <snapshot-id> --target run_differential --model ridge
DATABASE_URL=postgresql:///mlb_test uv run mlb experiment compare \
  --snapshot <snapshot-id>

# Feature selection stability report (filter + embedded stages)
DATABASE_URL=postgresql:///mlb_test uv run mlb experiment select-features \
  --snapshot <snapshot-id>

# Forward-stepwise feature selection (stage 3 nested chronological validation)
DATABASE_URL=postgresql:///mlb_test uv run mlb experiment select-features-stepwise \
  --snapshot <snapshot-id>

DATABASE_URL=postgresql:///mlb_test uv run mlb audit
```

For `home_win`, run the snapshot through `home_rate`, `log5`, `elo`,
`logistic`, `hist_gradient_boosting`, `xgboost`, `random_forest`,
`extra_trees`, `gam`, `svm`, and `bayesian`.
For `run_differential`, run through `zero`, `season_average`, `ridge`,
`hist_gradient_boosting_regressor`, `xgboost_regressor`,
`random_forest_regressor`, `extra_trees_regressor`, `gam_regressor`,
`svm_regressor`, and `bayesian_regressor`.
The report lists one result per calendar fold; compare like-for-like folds,
never a model's best isolated season against another model's total.

`svm`/`svm_regressor` scale worse than every other family here: kernel SVM
fitting is at least quadratic in training-row count, and `probability=True`
adds an internal 5-fold calibration on top of that (AGENTS.md: "SVMs where
dataset size permits", not unconditionally). Fitting them fold-by-fold
against a full production-scale snapshot (hundreds of thousands of rows per
training fold) is a real, practical resource concern the other families in
this list don't share. There's no code-level row cap — matching this file's
existing posture toward every other known-but-not-yet-enforced limitation
(e.g. `svm`'s own `probability=True` deprecation) — so bound the sample
deliberately when rehearsing these two specifically (`mlb_baseball.rehearsal
.load_sample`'s existing small, bounded multi-season sample, not a full
production-shaped snapshot).

`bayesian` (`GaussianNB`) can produce overconfident, badly miscalibrated
probabilities on a small per-fold training sample: it multiplies independent
per-feature Gaussian likelihoods with no regularization beyond a tiny
`var_smoothing` term, so a near-zero estimated variance in one feature can
push a prediction to (near-)0 or (near-)1 probability. Confirmed directly on
the bounded 2015/2024 rehearsal sample: `season-2015`'s log loss was exactly
`0.0000` (confidently and correctly certain), but `season-2024`'s was
`14.4175` — one confidently wrong call is catastrophic under log loss.
Other families can also reach an exact `0`/`1` probability on a small,
easy sample (confirmed directly: `RandomForestClassifier.predict_proba` can
return exactly `1.0`/`0.0` when every tree in the forest agrees), so this
isn't a claim that `bayesian` is uniquely capable of extreme confidence —
the specific risk here is *how easily* it gets there: `GaussianNB` has no
regularization at all on its per-class variance estimates, so a handful of
training rows is routinely enough, unlike the regularized linear families
(`logistic`/`ridge`/`gam`) or a tree ensemble reaching unanimous agreement
(a structurally different, comparatively rarer path to the same extreme
value). Watch for it specifically when comparing `bayesian` against other
families on small samples. Whether it behaves better at full production
scale, where per-class training counts are much larger, is a hypothesis
based on how `GaussianNB`'s variance estimates work, not a verified
result — confirm it against real production-scale folds (with the usual
calibration/uncertainty checks) before treating it as established, the same
bar any other family here would need to clear before promotion.

## Why the split is chronological

Random train/test splits let later games teach a model about earlier ones. The
default development folds test 2016 through 2024 one season at a time using
only preceding seasons for training. 2025 is untouched final holdout; 2026 is
forward monitoring, not model selection.

## Feature selection stability reporting

Feature selection evaluates the 11 `BASE_COLUMNS` candidate features across calendar
folds through three complementary stages:
1. **Stage 1 (filter)**: permutation importance against a linear baseline model
   (`logistic` for `home_win`, `ridge` for `run_differential`), evaluated against an
   injected synthetic normal noise column (`__noise__`).
2. **Stage 2 (embedded)**: tree-based feature importance from XGBoost models
   (`xgboost` / `xgboost_regressor`) against the same injected noise column.
3. **Stage 3 (forward-stepwise wrapper)**: nested chronological inner split
   (train on seasons $\le T-2$, validate on season $T-1$) inside each outer fold's
   training slice ($\le T-1$), evaluating only candidates that survived Stages 1 & 2
   in $\ge 70\%$ of evaluated folds. Each forward addition is tested against an
   injected permuted (shuffled) control variant, stopping when no candidate improves
   over shuffled noise.

Features surviving these stages across eras are reported as evidence of signal
stability. **These commands are purely diagnostic: they report evidence, and do not
select, drop, or alter what models train on.**

**Why no purging/embargo (2026-08-13, independent research review):** financial
ML's walk-forward validation typically adds a *purge* (drop training rows whose
label window overlaps the test window) and an *embargo* (a buffer after the
cut) because a label like "5-day-forward return" can straddle a fold boundary
even when features are point-in-time-safe. This project's targets (`home_win`,
`run_differential`) are resolved same-day and every feature is already
cutoff-safe, so there is no overlapping-label window to purge — a
season-boundary chronological split is sufficient by construction. Recorded
explicitly so a future reader doesn't have to re-derive why this project's
folds look simpler than the financial-ML literature's, rather than wondering if
it's a gap.

## Metrics, calibration, and nulls

For classification (`home_win`), Log loss and Brier score judge probability
quality. Accuracy is shown only as a secondary thresholded summary. Probability
calibration bins are retained.

For regression (`run_differential`), Mean Absolute Error (MAE) and Root Mean
Squared Error (RMSE) are primary, with deterministic 200-sample bootstrap 95%
confidence intervals. Residual calibration reports decile bins of predicted
values with mean prediction and mean residual (`actual - predicted`).

First-game record rates remain null: snapshots retain them, and common-row
scoring (`spec.required_columns`) reports excluded rows instead of filling them
silently. Python estimators use a documented median-plus-missing-indicator
preprocessing step.

## Add a model or target

1. Add target specifications in `TARGET_REGISTRY` (`TargetSpec`) or add an
   estimator branch in `_make_estimator`/`_validate_parameters`.
2. Use the shared snapshot, fold, scoring, and artifact path; do not add a
   model-specific training script.
3. Add unit/integration coverage proving null behavior, idempotency, and same-row
   comparison.
4. Update the feature registry and research record if the model needs inputs
   beyond `game_base_v1`.

Scikit-learn and XGBoost are the supported initial libraries. MLflow and Optuna
remain deferred: no broad search or external tracking service is justified
before this small contract demonstrates a real need.

The typed experiment configuration is bound to its snapshot's target,
`game_base_v1` version, source profile, calendar folds, seed, calibration
setting, parameters, and artifact location. Misspelled estimator parameters,
unsupported feature versions, malformed fold order, missing rows, and
time-overlapping folds fail clearly rather than silently producing a run.

## Current blockers before production experiments

- 2025 must remain untouched until a formal release gate.
- The lab has no model promotion, calibration fitting, broad hyperparameter
  search, market evaluation, or production prediction write path.
- Broader game/team/player/plate-appearance feature families require their own
  point-in-time contracts and tie-outs first.
