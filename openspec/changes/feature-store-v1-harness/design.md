## Context

See `proposal.md` — Why. The reusable walk-forward evaluation logic currently
lives in `mlb_baseball/model/experiment.py`:

- **Pure math, no I/O:** `folds()`, `_common_rows()`, `_matrix()`, `_labels()`,
  `_calibration()`, `_residual_calibration()`, `_metrics()`,
  `_regression_metrics()`, `_aggregate_metrics()`,
  `_aggregate_regression_metrics()`, and the chronological-cutoff separation
  check inside `run()`.
- **`mlb_baseball`-only, stays put:** `create_snapshot()` /`_snapshot_rows()` and
  everything touching `meta.experiment*`; `provenance` hashing and
  `_write_artifact()`; `_make_estimator()` (a ~220-line `sklearn`/`xgboost`
  zoo); `_validate_parameters()`; `TARGET_REGISTRY` and `SnapshotRow`;
  `_elo_probabilities()` / `log5` / `home_rate` / `zero` / `season_average`
  model families.
- **The one real coupling in the "pure" set:** `_calibration()` calls
  `sklearn.linear_model.LogisticRegression(C=1_000_000, …)` for the
  reliability-curve intercept and slope.

`mlb_research` (slice 1) already depends only on `duckdb`, `pandas`, and
`huggingface_hub`, and `mlb_baseball` now depends on `mlb_research`. Slice 1's
`get_historical_features` proved the pattern: copy the familiar shape (there,
Feast; here, a rolling-origin backtest), implement it small, keep the heavy
framework out.

## Goals / Non-Goals

**Goals:**

- One implementation of every evaluation primitive, in `mlb_research`, imported
  back by `mlb_baseball`.
- The `mlb-research` package fits no model and imports no model-training library.
- `mlb_baseball/model/experiment.py`'s public API and its `meta.experiment*`
  writes are behaviorally unchanged — proven by the existing
  `tests/integration/test_experiment.py` passing untouched.
- The harness takes a `pandas.DataFrame`, not a database connection or a
  `SnapshotRow`.

**Non-Goals:**

- Changing what `meta.experiment` / `meta.experiment_fold` store, the artifact
  JSON layout, `prediction_sha256`, or the experiment CLI.
- A general "pluggable estimator registry" in `mlb_research` — the callback pair
  is the whole extension surface.
- Online/streaming evaluation, nested CV, or hyperparameter search.
- Elo v2 or the model card (slice 3). This slice only makes their harness exist.

## Decisions

### D1 — Module: `mlb_research.backtest`, numpy + pandas only

One new module, `packages/mlb-research/mlb_research/backtest.py`. `numpy` becomes
a **direct** dependency of the package (it is already indirect via `pandas`);
nothing else is added. `scikit-learn` and `xgboost` appear only as **dev**
dependencies of `mlb-research`, used by the tie-out tests in D6, never imported
by `backtest.py`.

- *Alternative — put it in a new `mlb_research.eval` or a neutral `stats/`
  package.* `mlb_baseball/model/AGENTS.md` anticipates a neutral `stats/`
  boundary, but that is for descriptive baseball math; a backtest harness is an
  evaluation protocol and belongs with the shipped research toolkit. One module
  named for what it does.

### D2 — The seam: `run_backtest(frame, folds, fit_fn, predict_fn, *, task, ...)`

```python
BacktestResult = dataclass(folds: dict[str, FoldMetrics], aggregate: dict,
                           fold_plan: list[dict], coverage: dict, seed: int)

def run_backtest(
    frame: pd.DataFrame,              # one row per evaluation unit
    folds: Sequence[Fold],            # from time_ordered_folds(...)
    fit_fn: Callable[[pd.DataFrame], Model],
    predict_fn: Callable[[Model, pd.DataFrame], np.ndarray],
    *,
    task: Literal["classification", "regression"],
    time_col: str,                   # the cutoff timestamp column
    label_col: str,
    feature_cols: Sequence[str],
    required_cols: Sequence[str] = (),   # rows with a null here are excluded
    seed: int = 0,
) -> BacktestResult
```

Per fold: filter `frame` to train rows (`time_col` in the fold's train span) and
test rows (`time_col` in the test span); assert
`max(train[time_col]) < min(test[time_col])` (the chronological-separation check
lifted verbatim from `run()`); drop rows missing a `required_cols` value and
count them; `model = fit_fn(train)`; `p = predict_fn(model, test)`; score with
the D5 metrics seeded by `seed + <test period>`. `fit_fn` / `predict_fn` receive
**DataFrames** (not numpy matrices) so a caller keying on `game_instance_key` or
walking rows in `time_col` order (Elo) has what it needs; a plain sklearn caller
does `df[feature_cols].to_numpy()` in its two-line callback.

- *Alternative — pass numpy matrices to the callbacks.* Loses the row identity
  and ordering a sequential model needs, and forces the harness to own the
  feature-selection step that is really the caller's.
- *Alternative — a `Model` protocol with `.fit()` / `.predict_proba()`.* That is
  the sklearn interface; adopting it as ours drags sklearn's shape (and the
  `predict_proba()[:, 1]` convention, the regression/classification split by
  method name) into the contract. Two functions are smaller and testable.

### D3 — Sequential models (Elo) use the same seam

A stateful predictor fits its state on the chronologically-ordered train frame
and then, inside `predict_fn`, walks the test rows in `time_col` order,
emitting each prediction **before** folding that game's result into its state.
This is exactly what `_elo_probabilities()` does today (it takes `all_rows`, but
the pre-test portion is just the train rows). It is leak-free because every
prediction precedes its own update. The harness does not need an "online" mode;
it needs `predict_fn` to receive the test rows in cutoff order, which it
guarantees.

- *Alternative — a third `sequential_fn(ordered_frame, test_mask)` callback.*
  More surface for a case the two-callback form already covers. Rejected unless
  slice 3's Elo v2 actually cannot express itself in `predict_fn` — recorded as
  an open question, not a design commitment.

### D4 — `time_ordered_folds()` replaces `folds()`, season-keyed for now

```python
def time_ordered_folds(test_periods: Sequence[int], *, key: str = "season") -> tuple[Fold, ...]
```

Same semantics as `experiment.folds()`: for each `test_period`, train is
everything strictly before it. `Fold` keeps `name` / `train_through` / `test`
fields. Keyed on an integer period column (season) in v1; a date-range variant
is a later addition and does not change the signature's shape. `experiment.folds()`
becomes `return time_ordered_folds(fold_years)` — same tuple, same validation
(unique, sorted).

- *Alternative — arbitrary date-boundary folds now.* No caller needs them this
  slice; season folds are what every existing experiment and the slice-3 model
  card use. Add the date variant when a caller needs it.

### D5 — Metrics reimplemented in numpy; sklearn tie-out is a test, not a dep

| Function | numpy form |
| --- | --- |
| log loss | `-mean(y*log(p̂) + (1-y)*log(1-p̂))`, `p̂ = clip(p, 1e-15, 1-1e-15)` |
| Brier | `mean((p - y)**2)` |
| accuracy | `mean((p >= 0.5) == y)` |
| MAE / RMSE | `mean(|y-ŷ|)` / `sqrt(mean((y-ŷ)**2))` |
| reliability bins | unchanged — pure numpy already |
| bootstrap 95% CI | unchanged — `random.Random(seed)` resampling |
| calibration intercept/slope | **new:** 1-D logistic regression by IRLS (Newton-Raphson), ~15 lines, unregularized to match `C=1e6`, deterministic, capped iterations |

A dev-only test imports `sklearn.metrics` and `sklearn.linear_model` and asserts
the numpy results match on a fixed fixture within `1e-6` (metrics) and `1e-3`
(IRLS slope/intercept vs. `C=1e6` logistic). The hand-calculated fixtures in
`tests/unit/test_experiment_metrics.py` (`brier == 0.0625`,
`log_loss == -log(0.75)`, `mae == 1.25`) move with the code and must pass
identically.

- *Alternative — keep `_calibration` calling sklearn and make sklearn a real
  `mlb-research` dependency.* Defeats the requirement; sklearn + its transitive
  scipy is exactly the weight an analyst should not be forced to install to read
  a reliability table.
- *Alternative — drop the intercept/slope, ship only the bins.* The
  intercept/slope is the one-number summary a model card quotes; keep it.

### D6 — `experiment.py` becomes an adapter; pure-math names are re-exports

`experiment.py` keeps every public name. Internally:

- `_snapshot_rows()` → build a `pd.DataFrame` (`game_instance_key`, `season`,
  `feature_cutoff_at`, one column per `BASE_COLUMNS` entry, the label).
- The `elo` / `log5` / `home_rate` / `zero` / `season_average` families and the
  `_make_estimator()` zoo each become a `(fit_fn, predict_fn)` factory. The
  sklearn zoo's factory is `fit_fn = lambda df: est.fit(df[cols].to_numpy(),
  df[label].to_numpy())`, `predict_fn = lambda est, df:
  est.predict_proba(df[cols].to_numpy())[:, 1]`.
- `run()` calls `mlb_research.backtest.run_backtest(...)`, then does the
  identical `meta.experiment*` inserts, artifact writes, `provenance.git_sha()`,
  resume/failed-run handling it does today.
- `_calibration`, `_metrics`, `_common_rows`, `folds`, … →
  `from mlb_research.backtest import calibration as _calibration` (etc.), so
  there is one definition and `tests/unit/test_experiment_metrics.py`'s imports
  still resolve.
- `_common_rows(rows, spec)` currently reads `spec.required_columns`; the
  adapter passes `spec.required_columns` as `required_cols` to the harness.

- *Alternative — delete `experiment.folds` / `_metrics` etc. and update every
  caller.* Breaks `test_experiment_metrics.py` and any notebook importing them
  for no benefit; a re-export is one line and keeps the facade.

### D7 — Dependency & boundary bookkeeping

- `packages/mlb-research/pyproject.toml`: add `numpy>=1.26` to
  `dependencies`; add `scikit-learn` to a `[project.optional-dependencies].dev`
  (or the test group the repo uses) for the tie-out test only.
- `mlb_baseball/model/AGENTS.md`: record that the pure evaluation math now lives
  in `mlb_research.backtest` and `experiment.py` is its `mlb_baseball`-side
  adapter.
- No ADR: this does not scope a root invariant the way slice 1's DuckDB boundary
  did. It is the dependency direction slice 1 already established, applied once
  more.

## Risks / Trade-offs

- **Metric drift changes a stored `meta.experiment` number.** → The
  integration assertions are structural (`0 <= brier <= 1`, `log_loss > 0`, row
  counts); the numpy forms are the textbook definitions sklearn also implements;
  the tie-out test pins them within `1e-6`. `prediction_sha256` is hashed from
  predictions, not metrics, so artifact identity is unaffected.
- **IRLS diverges on a degenerate fold** (perfect separation, one class). →
  Match the existing guard: `_calibration` already returns
  `intercept=slope=None` when `len(y) < 20` or `< 2` classes; keep that, and cap
  IRLS iterations with a fallback to `None` on non-convergence.
- **A slice-3 Elo v2 that truly needs online state across the fold boundary.** →
  D3's open question; if real, add a `sequential_fn` seam then. It does not
  change this slice's specs or tasks.
- **`mlb_baseball` import-time cost.** → `experiment.py` already imports sklearn
  and xgboost at module scope; importing `mlb_research.backtest` (numpy only) on
  top is negligible and the heavy imports stay lazy-able exactly as now.

## Open Questions

- Does slice 3's Elo v2 express itself within `predict_fn` (walk test rows in
  cutoff order, predict-then-update), or does it need a dedicated sequential
  callback? Answerable when Elo v2 is written; if it needs the extra seam, that
  is an additive change to `run_backtest`'s signature, not a spec change.
- Which existing test group in `packages/mlb-research/pyproject.toml` should
  carry the `scikit-learn` tie-out dependency (there may not be one yet) — a
  packaging detail for the apply step.
