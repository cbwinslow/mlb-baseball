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
matches published modern-era RE24 values allowing for real run-environment
spread across cited eras (e.g. bases loaded/0 outs 2.430 vs. FanGraphs'
2.282 baseline — see ADR-076 for the full cited comparison protocol).
Second package landed the same day (ADR-077): `simulate_half_inning`/
`simulate_half_innings` Monte Carlo-sample half-innings from the estimated
outcome distribution; `real_half_inning_runs` computes the real historical
per-half-inning run distribution to compare against. Verified three
independent ways against real 2019 `mlb` data (43,346 complete
half-innings, excluding 205 walk-off-truncated ones that never reach 3
outs, a real, non-negligible bias a PR review caught): real mean (0.534)
and simulated mean (0.552) differ by ~3.4% (the largest of the three
pairwise gaps), and both closely match `run_expectancy`'s
independently-computed bases-empty/0-outs value (0.542) — three
different code paths (linear solve, Monte Carlo walk, direct real-data
aggregate) landing within ~3.4% of each other. Third package landed the
same day (ADR-078): `simulate_game` plays a full game of `regulation_innings`
length (9 by default, configurable — or longer, on a tie), both teams
alternating, applying real game-ending rules — a walk-off ends the game
mid-half-inning the instant the home team takes the lead at or past
`regulation_innings`, and an already-decided game skips a needless
bottom half — via a new lower-level `simulate_half_inning_steps`
primitive; `real_game_scores` computes real final scores from
`raw.retrosheet_gameinfo`'s own `vruns`/`hruns` columns. Verified as an
in-sample diagnostic against real 2019 `mlb` data (2,429 games):
total-runs mean real 9.66 vs. simulated 9.83 (~1.7%), innings-played
mean real 9.19 vs. simulated 9.17 (~0.2%), extra-innings rate real 8.56%
vs. simulated 8.36% (~2.4% relative) — all close summary statistics, not
a distribution-distance metric. Home win rate is the one honestly-reported gap:
real 52.9% (real baseball's well-documented home-field advantage) vs.
simulated 49.9% (a coin flip, expected — the simulator uses one
league-average distribution for both teams, no home/away split).
Fourth package landed the same day (ADR-079): a genuinely held-out
calibration check — `scripts/verify_markov_calibration.py
--estimate-seasons 2015 2016 2017 2018 --season 2019` estimates from
seasons strictly before 2019 and compares against real 2019, closing
the in-sample gap the first three packages flagged. Every scoring/timing
gap widened honestly (half-inning mean ~5.2% vs. in-sample ~3.4%;
total-runs mean ~5.7% vs. in-sample ~1.7%; extra-innings rate ~18.8%
relative vs. in-sample ~2.4%) — root cause verified directly: real
average runs/game rose from 8.50 (2015) to 9.66 (2019), and the held-out
model, trained only on the lower-scoring 2015-2018 average, predicts
9.11, honestly missing 2019's real offensive spike rather than having
learned it. Home win rate is the exception — it narrowed slightly
(held-out 50.5% vs. real 52.9%, a 2.4-point gap, versus in-sample's
3.0-point gap), not meaningful given a single ~2,429-game sample, and a
separate limitation (no home/away split) that held-out estimation
doesn't meaningfully affect either way. Fifth package (ADR-080):
`estimate_outcome_distribution` gained an optional `bat_home` filter and
`simulate_game` an optional `home_distribution` parameter, closing that
home/away gap — verified the premise first (2019 alone showed no real
home/away scoring difference, an anomaly; 2015-2018 all showed a real
one, e.g. 2017 home batters scored on 3.32% of plate appearances vs.
away batters' 3.09%), then verified the fix: split-distribution home
win rate landed at 52.6% (vs. the original combined-distribution
49.9%), a ~8x reduction in the gap from real 52.9%, stable across
multiple seeds. Not yet built: whether the home/away split's benefit
holds out-of-sample too (ADR-079 tested the combined-distribution
approach only), understanding why the split closes the gap despite the
two sides' simulated run means coming out nearly identical (ADR-080's
own open question), and precise walk-off run crediting (ADR-078's
Revisit-if).

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
