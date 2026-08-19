# Plan 04 — Modeling, Markov simulation, and guided experimentation

## Objective

Create a reproducible breadth-and-depth modeling laboratory that can discover
useful signals while resisting leakage, overfitting, and false discovery.

**Status:** 04A/04B foundation and 04E feature-selection pipeline (stages 1-3)
active in `mlb_test` only. The reusable experiment laboratory supports target-agnostic
execution (`home_win` classification and `run_differential` regression), fixed calendar
folds, content-addressed snapshots, transparent baselines, scikit-learn/XGBoost
estimators (logistic/ridge, HistGradientBoosting, XGBoost, random forest/extra
trees added 2026-08-18, `gam`/`gam_regressor` added 2026-08-18 — a
spline-expanded logistic/ridge pipeline closing 04C's "GAM" requirement with
no new dependency — `svm`/`svm_regressor` added 2026-08-18, closing 04C's
"SVMs on appropriately bounded samples" requirement, `bayesian`/
`bayesian_regressor` added 2026-08-19 (`GaussianNB`/`BayesianRidge`, no new
dependency), closing 04C's "Bayesian" requirement specifically (ADR-074),
and `neural`/`neural_regressor` added 2026-08-19 (`MLPClassifier`/
`MLPRegressor`, no new dependency), closing 04C's "neural" requirement
specifically (ADR-075) — see those ADRs' "Declined" sections for why true
hierarchical/multilevel partial-pooling and true sequence/embedding models
remain distinct, still-open gaps, not covered by either), permutation filter
(stage 1), tree-embedded (stage 2), and forward-stepwise wrapper with nested
chronological splits (stage 3) feature stability reporting, and persisted
evidence. It does not promote or write a production forecast. Remaining 04C
families not yet built: true hierarchical/multilevel (partial-pooling)
models and true sequence/embedding models (recurrent/attention architectures
over a sequential, not flat per-game, feature representation).

**04D status:** first package landed 2026-08-19 — `mlb_baseball/model/markov.py`
estimates the 24-state base/out transition matrix and its RE24-style run-
expectancy table directly from `raw.retrosheet_event` (ADR-076; `core.play`
alone cannot, it has no runner-on-base columns — a correction to
`docs/RESEARCH.md`'s prior claim). Verified against real `mlb` data: closely
matches published modern-era RE24 values (e.g. bases loaded/0 outs 2.430 vs.
published ~2.28-2.42). Not yet built: the half-inning/game simulator and
calibration against held-out real seasons.

## Work packages

### 04A — Experiment platform

Version datasets, folds, features, code, parameters, seeds, artifacts, metrics,
resource use, and status. Support queued/resumable sweeps, early pruning, failure
capture, comparison reports, and champion/challenger promotion. Begin with the
project registry; evaluate MLflow/Optuna only through bounded zero-cost spikes.

### 04B — Target ladder and baselines

Define labels/cutoffs/metrics for pitch, plate appearance, base/out transition,
inning/team runs, full-game distribution/winner/totals/run line, player-game
props, and season projections. Establish empirical, league-rate, log5/Elo,
regularized GLM, GAM, and shrinkage/hierarchical baselines before complex models.
Every target declares its game-instance identity, observation time, feature
availability cutoff, and outcome-resolution rule; no evaluation may join only
on an ambiguously reused external game ID.

**First contract:** development folds test 2016–2024 one season at a time,
training only through the preceding season. 2025 is reserved final holdout and
2026 is forward monitoring. Log loss and Brier score are primary; accuracy is
secondary. No random split is allowed.

### 04C — Model families

Evaluate regularized regression, random forests/extra trees, gradient boosting,
SVMs on appropriately bounded samples, Bayesian/hierarchical approaches, and
neural/sequence/embedding models where structure and data justify them. Use the
same immutable folds and metrics; complexity receives no preferential treatment.

### 04D — Markov and simulation engine

Estimate base/out transition matrices and run expectancy by context; validate
probabilities and conservation rules; simulate plate appearances, innings, games,
first-five, team totals, totals, run lines, and player outcomes. Calibrate composed
distributions against held-out seasons and real forward results.

### 04E — Guided search and interactions

Run research-prioritized feature families first, then mathematically justified
exploration. Use nested rolling-origin selection, stability across eras/seasons,
ablation, permutation/SHAP diagnostics, multiple-comparison awareness, and compute
budgets. Search is broad; promotion is strict.

### 04F — Ensembles and stacking

Combine complementary, calibrated models only with out-of-fold base predictions.
Compare averaging, weighted blends, and meta-learners to the best single champion.
Reject stacks whose gains are unstable, operationally expensive, or caused by
leakage. Publish disagreement and uncertainty as useful product signals.

### 04G — Research-to-product scorecards

Publish internal model cards before public forecasts: matched-sample log loss,
Brier, calibration, coverage, era/segment stability, market comparison, feature
schema, artifact/data cutoff, and known missing-input behavior. A model that
cannot beat transparent baselines or explain its coverage remains a research
result, not a promoted forecast.

## Acceptance gate

- Every result is reproducible from IDs/configuration and a clean environment.
- Final holdouts remain untouched until a declared gate; forward monitoring uses
  one prediction per target/cutoff.
- Models report calibration, proper scores, uncertainty, coverage, and segment/
  era stability—not cherry-picked accuracy.
- Stacking tests prove base predictions are out-of-fold.
- Prediction history preserves one declared pregame snapshot per game instance
  and cannot be rewritten or conflated by duplicate external IDs.
- At least one trustworthy champion exists per promoted target; unsuccessful
  targets remain research outputs rather than fabricated products.
