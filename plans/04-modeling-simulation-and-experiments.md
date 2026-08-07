# Plan 04 — Modeling, Markov simulation, and guided experimentation

## Objective

Create a reproducible breadth-and-depth modeling laboratory that can discover
useful signals while resisting leakage, overfitting, and false discovery.

**Status:** Queued (depends on Plan 03).

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
