## Why

The `delivery` capability requires that an installing analyst can reproduce the
reference baseline's model card "running the walk-forward backtest harness the
distribution ships against their own build." That harness exists — inside
`mlb_baseball/model/experiment.py`, a 1,586-line module that imports `psycopg`,
`sklearn`, and `xgboost` at module scope and reads its evaluation frame straight
out of PostgreSQL (`meta.experiment_snapshot`). None of it is installable by an
outside analyst, and none of it runs without a database server and the full
model-training stack. Slice 3 (Elo v2 + model card) cannot produce a
reproducible card until the harness it depends on ships in `mlb_research`.

This is **slice 2 of 3** of the v1.1 platform work (`feature-store-v1` roadmap).
Slice 1 shipped the DuckDB feature store and inverted the dependency direction so
`mlb_baseball` depends on `mlb_research`. This slice moves the harness across
that same direction: one implementation, both products.

## What Changes

- **A new `mlb_research.backtest` module** — the walk-forward evaluation harness,
  **numpy + pandas only**:
  - `time_ordered_folds(...)` — rolling-origin folds keyed on a season/date
    column; train is always strictly before test; a random split is not
    expressible.
  - as-of frame assembly — take a single tidy `DataFrame` (one row per game, a
    cutoff-timestamp column, feature columns, a label column) and yield the
    per-fold train/test matrices, dropping rows with a null required input
    rather than imputing.
  - the fit / score loop — for each fold call a **caller-supplied
    `fit_fn(X_train, y_train) -> model` and `predict_fn(model, X_test) ->
    probabilities`**, so `sklearn`, `xgboost`, `PyMC`, or a hand-written Elo all
    become the *caller's* dependency, never the package's.
  - probability-quality metrics — log loss, Brier, a 10-bin reliability
    (calibration) table with an intercept/slope from a numpy 1-D logistic fit,
    accuracy, and bootstrap 95% CIs; the regression counterparts (MAE, RMSE,
    residual-decile calibration).
  - `paired_comparison(...)` — the matched-sample "common games" comparison of
    two probability vectors over exactly the games both models scored.
  - a `BacktestResult` dataclass — per-fold and aggregate metrics, the fold
    plan, the row/exclusion counts, and the seed, JSON-serializable for a model
    card.
- **`mlb_baseball/model/experiment.py` becomes a thin adapter.** Its public API
  is unchanged — `run()`, `compare()`, `create_snapshot()`, `folds()`,
  `ExperimentConfig`, `snapshot_integrity()`, `health_check()` all keep their
  signatures and behavior. Internally it builds the frame from
  `meta.experiment_snapshot`, wraps its `sklearn`/`xgboost` estimator zoo and
  the `elo` / `log5` / `home_rate` families as `fit_fn` / `predict_fn` pairs,
  calls `mlb_research.backtest`, and writes the returned metrics to
  `meta.experiment*` exactly as today. The estimator zoo, parameter validation,
  snapshot machinery, provenance hashing, and all PostgreSQL access **stay in
  `mlb_baseball`**.
- **The pure-math evaluation functions leave `mlb_baseball`.** `_calibration`,
  `_residual_calibration`, `_metrics`, `_regression_metrics`, `_common_rows`,
  `_matrix`, `_labels`, and the fold-loop core move to `mlb_research.backtest`;
  `experiment.py` imports them back so there is one definition. The
  `sklearn.linear_model.LogisticRegression` call inside `_calibration` is
  replaced by a ~15-line numpy IRLS fit (deterministic, no dependency).
- **`mlb_research` gains no new runtime dependency.** It already declares
  `pandas`; this adds `numpy` (already an indirect dependency via pandas, now
  made direct). No `sklearn`, no `xgboost`.

Out of scope: Elo v2 and the model card (slice 3); the notebook recipes and the
Hugging Face publish wiring (slice 3); re-parenting `gold.game_feature`;
consolidating `meta.feature_snapshot` / `meta.experiment_snapshot`; any change to
what `meta.experiment` stores or to the experiment-lab CLI surface; hyperparameter
search or model promotion logic.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `delivery`: add one requirement to the "research platform" surface — **the
  shipped backtest harness is model-agnostic and dependency-light**. It lives in
  the installable `mlb-research` package; model fitting is a caller-supplied
  callback pair, so the package itself imports no model-training library; its
  folds are strictly time-ordered (a random split is not expressible); it runs
  from a plain DataFrame with no database connection; and it reports probability
  quality (log loss, Brier, calibration), not accuracy alone. This is what makes
  the existing "analyst reproduces the model card with the shipped harness"
  clause satisfiable.

## Impact

- **New:** `packages/mlb-research/mlb_research/backtest.py` (~450 lines: ~200
  genuinely new — the numpy metric/IRLS reimplementations and the callback seam
  — the rest moved verbatim); `packages/mlb-research/tests/test_backtest.py`;
  `numpy` as a direct dependency in `packages/mlb-research/pyproject.toml`.
- **Changed:** `mlb_baseball/model/experiment.py` (pure-math functions become
  re-exports; `_probabilities` / `_predictions` split into estimator-zoo
  `fit_fn`/`predict_fn` factories + a call into the shared harness); possibly
  `mlb_baseball/model/__init__.py` if it re-exports any moved symbol.
- **Docs:** `docs/RESEARCH.md` (the harness is now a shipped surface, with its
  time-ordering and callback contract); `docs/PUBLIC_API.md` and
  `packages/mlb-research/README.md` (the new `mlb_research.backtest` API);
  `mlb_baseball/model/AGENTS.md` (the pure-math boundary moved to
  `mlb_research`); the `feature-store-v1` roadmap note that slice 2 is done.
- **Unchanged:** every `meta.experiment*` table and its contents; the experiment
  CLI; `model/elo.py`, `model/log5.py`; all connector, ingestion, and conform
  code; the DuckDB feature store from slice 1.
- **Tests:** `mlb_research` unit tests gain deterministic hand-fixture coverage
  of folds, metrics, the IRLS calibration fit (tie-out against the old sklearn
  numbers within tolerance), and the paired comparison. `test_experiment.py`
  integration tests must still pass unchanged — the behavioral proof that the
  adapter preserves the facade.
