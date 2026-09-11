Scope: **slice 2 of 3** — extract the walk-forward backtest harness from
`mlb_baseball/model/experiment.py` into `mlb_research.backtest`, numpy + pandas
only, model fitting via a caller-supplied `fit_fn` / `predict_fn`. `experiment.py`
becomes the `mlb_baseball`-side adapter with its public API and `meta.experiment*`
writes unchanged. Elo v2 + the model card are slice 3.

TDD applies to every task that adds behaviour: write the failing test, watch it
fail for the right reason, then make it pass. Tasks marked **[OWNER]** are the
owner's to run and are recorded, not gated in CI.

## 1. Package setup

- [x] 1.1 Add `numpy>=1.26` to `[project].dependencies` in
  `packages/mlb-research/pyproject.toml`; add `scikit-learn` to the package's
  dev/test dependency group (create one if none exists) for the tie-out tests
  only. Verify: `uv sync` resolves; `uv run python -c "import numpy, mlb_research"`
  works; `uv run python -c "import mlb_research.backtest"` (once the module
  exists) shows neither `sklearn` nor `xgboost` in `sys.modules` (subprocess
  check, per slice 1's pattern).
- [x] 1.2 Create `packages/mlb-research/mlb_research/backtest.py` with the module
  docstring stating the contract (model-agnostic, time-ordered only, no DB, no
  model-training import) and the `Fold` / `FoldMetrics` / `BacktestResult`
  dataclasses from design D2. Verify: `import mlb_research.backtest` succeeds;
  `ruff` + `mypy` clean.

## 2. Folds and frame assembly

- [x] 2.1 Failing test `packages/mlb-research/tests/test_backtest.py`:
  `time_ordered_folds([2016, 2017])` returns two folds, train-through 2015/2016,
  and rejects unsorted or duplicate periods. Port
  `test_calendar_folds_are_strictly_ordered` verbatim against the new name.
  Verify: RED then GREEN.
- [x] 2.2 Implement `time_ordered_folds(test_periods, *, key="season")` (design
  D4) — same semantics and validation as `experiment.folds()`. Verify: 2.1
  passes.
- [x] 2.3 Failing test: given a frame with a null in a `required_cols` column,
  that row is excluded from train and test and counted; a rate column is
  selected by name, not positionally. Verify: RED then GREEN.
- [x] 2.4 Implement the per-fold frame split: filter by `time_col` span, assert
  `max(train[time_col]) < min(test[time_col])` (lifted from `run()`), drop and
  count `required_cols`-null rows. Verify: 2.3 passes; the separation assertion
  raises on an overlapping fixture.

## 3. Metrics in numpy

- [x] 3.1 Move `tests/unit/test_experiment_metrics.py`'s
  `test_probability_metrics_match_hand_calculation_and_are_deterministic` and
  `test_regression_metrics_match_hand_calculation_and_are_deterministic` into
  `test_backtest.py` against `mlb_research.backtest` (`brier == 0.0625`,
  `log_loss == -log(0.75)`, `mae == 1.25`, `rmse == 1.5`, determinism on a
  fixed seed). Verify: RED (no module) then GREEN.
- [x] 3.2 Implement `classification_metrics(y, p, seed)` and
  `regression_metrics(y, ŷ, seed)` in numpy (design D5 table): log loss, Brier,
  accuracy / MAE, RMSE; the existing reliability-bin and bootstrap-CI code moved
  verbatim; the finite-in-`[0,1]` guard preserved. Verify: 3.1 passes.
- [x] 3.3 Implement `calibration(y, p)` — reliability bins (moved verbatim) plus
  the intercept/slope from a numpy IRLS 1-D logistic fit, keeping the
  `len(y) < 20` / `< 2 classes` → `None` guard and adding an
  iteration-cap → `None` fallback on non-convergence. Verify: a unit test on a
  fixture with a known separable-ish signal asserts a positive slope and finite
  intercept; the small-sample fixture still returns `None`.
- [x] 3.4 Tie-out test (imports `sklearn`): on one fixed fixture,
  `classification_metrics` matches `sklearn.metrics.log_loss` /
  `brier_score_loss` / `accuracy_score` within `1e-6`, and `calibration`'s
  slope/intercept match `LogisticRegression(C=1e6, …)` within `1e-3`. Verify:
  the test passes; it is in the dev/test group so CI without sklearn skips it
  cleanly (or sklearn is in the CI test env — state which).
- [x] 3.5 Move `_aggregate_metrics` / `_aggregate_regression_metrics` and
  `test_aggregate_regression_metrics_weighted_by_rows` (`mae == 3.5`,
  `rmse == 4.5`). Verify: the ported test passes.

## 4. The fit/score loop and the paired comparison

- [x] 4.1 Failing test: `run_backtest` over a 2-fold synthetic frame with a
  trivial `fit_fn` (returns the train mean) / `predict_fn` (broadcasts it)
  returns per-fold + aggregate metrics, the fold plan, and coverage counts; the
  aggregate row count equals the summed test rows. Verify: RED then GREEN.
- [x] 4.2 Implement `run_backtest(frame, folds, fit_fn, predict_fn, *, task,
  time_col, label_col, feature_cols, required_cols=(), seed=0) -> BacktestResult`
  (design D2): per-fold split (task 2.4), `fit_fn` / `predict_fn`, metrics
  seeded `seed + test_period`, `coverage` dict with snapshot/common/excluded
  counts, aggregate. Verify: 4.1 passes; `run_backtest` never imports a
  model-training library (subprocess `sys.modules` check).
- [x] 4.3 Failing test: `paired_comparison(pred_a, pred_b, y, keys_a, keys_b)`
  scores both models only over the intersecting keys and reports that count.
  Port the intent of `test_common_rows_filters_per_target_spec` /
  `experiment.compare`'s matched-sample logic. Verify: RED then GREEN.
- [x] 4.4 Implement `paired_comparison(...)` and move `_common_rows`'s
  column-null filter as a reusable `drop_incomplete(frame, required_cols)`.
  Verify: 4.3 passes.
- [x] 4.5 Sequential-model check (design D3): a test where `fit_fn` fits a
  running mean on the chronologically-ordered train frame and `predict_fn`
  walks test rows in `time_col` order predicting-then-updating produces the
  same result as a hand roll, and no future row influences an earlier
  prediction. Verify: RED then GREEN — this is the assertion that Elo v2 (slice
  3) relies on.

## 5. `experiment.py` becomes the adapter

- [x] 5.1 Re-export the moved names: `from mlb_research.backtest import (...)` as
  `folds`, `_metrics`, `_regression_metrics`, `_calibration`,
  `_residual_calibration`, `_aggregate_metrics`, `_aggregate_regression_metrics`,
  `_common_rows` (adapting the `spec` arg to `required_cols`). Verify: the
  remaining `tests/unit/test_experiment_metrics.py` imports resolve and its
  non-moved tests (`test_target_registry_specifications`,
  `test_validate_parameters_*`, `test_make_estimator_*`) still pass.
- [x] 5.2 Build the evaluation `DataFrame` from `_snapshot_rows()` inside `run()`
  (`game_instance_key`, `season`, `feature_cutoff_at`, one column per
  `BASE_COLUMNS`, the label). Verify: a unit test asserts the frame's columns,
  dtypes, and row count for a small `SnapshotRow` list.
- [x] 5.3 Turn each model family into a `(fit_fn, predict_fn)` factory: the
  `_make_estimator` sklearn/xgboost zoo, plus `elo` (fit ratings on the ordered
  train frame; `predict_fn` walks test rows predicting-then-updating — same math
  as `_elo_probabilities`), `log5`, `home_rate`, `zero`, `season_average`.
  Verify: a unit test per family that its `predict_fn` output matches the
  current `_probabilities` / `_predictions` output on a fixed fixture.
- [x] 5.4 Rewrite `run()`'s fold loop as a `run_backtest(...)` call, keeping
  every `meta.experiment` / `meta.experiment_fold` insert, `_write_artifact`,
  `provenance.git_sha()`, resume, and failed-run path exactly as before. Verify:
  `tests/integration/test_experiment.py` passes **unchanged** (row counts,
  `aggregate["rows"] == 14`, fold names, artifact SHA naming, resume, failed
  run, `compare`).
- [ ] 5.5 **BLOCKED on an owner decision -- not implemented as written.**
  `compare()`'s current flat per-model-per-fold `metrics_json` listing is a
  real, load-bearing CLI feature: `mlb experiment compare --snapshot <id>`
  (`experiment_commands.add_parser("compare", help="show saved fold
  metrics")` in `cli.py`) prints `row['model']`/`row['fold']` plus
  `_format_metrics_line(row)`, which reads `log_loss`/`brier` or
  `mae`/`rmse` directly off each row. A `paired_comparison`-based rewrite is
  inherently pairwise (it scores exactly two models' predictions over their
  common keys) and cannot produce that same flat single-model-per-row shape
  without either breaking `_format_metrics_line` or `compare()` silently
  becoming a different, differently-shaped function. This also contradicts
  `proposal.md`'s own "What Changes": "Its public API is unchanged —
  `run()`, `compare()`, ... all keep their signatures **and behavior**."
  `compare()` is left unchanged (still reads `meta.experiment_fold
  .metrics_json`, not raw predictions) pending an owner decision on one of:
  (a) keep `compare()` as-is and treat `paired_comparison` as a
  `mlb_research`-shipped utility with no `mlb_baseball` caller yet (it is
  still directly tested in `packages/mlb-research/tests/test_backtest.py`,
  task 4.3/4.4); (b) add a **new** CLI subcommand/function for the
  matched-sample pairwise comparison, leaving `compare()`'s existing output
  and CLI behavior untouched; (c) accept breaking `mlb experiment compare`'s
  current output shape as a deliberate, documented behavior change (update
  `cli.py`, `docs/EXPERIMENT_RUNBOOK.md`, and this proposal's "unchanged"
  claim together). Verify (once decided): the chosen option's exact
  contract, plus `tests/integration/test_experiment.py`'s
  `assert any(row["model"] == model_family for row in comparison)` and any
  CLI dispatch test for `experiment compare`.
- [x] 5.6 Removed `_probabilities` / `_predictions` / `_elo_probabilities`
  (superseded by `_estimator_factory` + `run_backtest`, task 5.4).
  `_calibration` / `_metrics` / `_regression_metrics` / `_aggregate_metrics` /
  `_aggregate_regression_metrics` were already re-exports (task 5.1), not
  local defs to remove. **`_matrix` / `_labels` kept** -- `ruff` alone
  wouldn't have caught this: `mlb_baseball/model/feature_select.py` and
  `feature_select_stepwise.py` import both directly for their own
  SnapshotRow-based stepwise/stability estimator fitting, a separate
  pipeline this slice doesn't touch. Discovered by running the unit suite
  after the initial deletion (`ImportError: cannot import name '_labels'`),
  not by `ruff`/`grep`/`mypy mlb_baseball` alone -- ruff and mypy only see
  `experiment.py` itself, not cross-module importers; the task's own verify
  list was insufficient by itself. Verify done: `ruff check` + `ruff format`
  + `mypy mlb_baseball/model/experiment.py` clean; `grep` for a shadowing
  local def of the re-exported names is empty;
  `tests/unit/` (1226 passed), `tests/integration/test_experiment.py` +
  `test_feature_select.py` + `test_feature_select_stepwise.py` all green
  (real PostgreSQL).

## 6. Documentation

- [x] 6.1 `packages/mlb-research/README.md`: a "Backtesting" section — the
  `run_backtest` / `time_ordered_folds` / `paired_comparison` signatures, the
  `fit_fn` / `predict_fn` contract, a copy-pasteable sklearn-callback example
  and a no-sklearn (numpy Elo-style) example. Verify: both examples run in a
  clean env with `mlb-research` + `numpy` only (the sklearn one needs sklearn).
- [x] 6.2 `docs/PUBLIC_API.md`: add `mlb_research.backtest` to the consuming
  surface. `docs/RESEARCH.md`: the harness is now a shipped, model-agnostic
  surface — its strict time-ordering, the callback seam, "probability quality
  not accuracy". `mlb_baseball/model/AGENTS.md`: the pure evaluation math lives
  in `mlb_research.backtest`; `experiment.py` is its adapter. Verify:
  `mkdocs build --strict` clean; the AGENTS.md child-index / DOX check passes.
- [x] 6.3 Note slice 2 done in the `feature-store-v1` roadmap
  (`proposal.md` — Roadmap) or wherever the roadmap now lives, and update
  `openspec/project.md`'s `NOW / NEXT / LATER` if it tracks the slices. Verify:
  `openspec validate --all` passes.

## 7. Verification

- [x] 7.1 Exit codes recorded (no PR opened yet; recorded here + in this
  session's commits instead): `openspec validate --strict
  feature-store-v1-harness` → 0. `pre-commit run --all-files` → 0 (11 hooks,
  all Passed). `ruff check` on this session's touched Python files
  (`mlb_baseball/model/experiment.py`,
  `packages/mlb-research/mlb_research/backtest.py`,
  `packages/mlb-research/tests/test_backtest.py`,
  `tests/unit/test_experiment_metrics.py`) → 0. `ruff format --check` on all
  13 files this session touched (`git diff --stat
  fd1f77b..HEAD`) → 0. `mypy mlb_baseball/model/experiment.py` → 0. `mypy
  packages/mlb-research/mlb_research/backtest.py` → 0. Note: a whole-repo
  `ruff format --check .` also flags 7 **pre-existing, untouched** files
  (`docs/archive/superpowers-plans/*`, `docs/research/2026-09-04-*`,
  `openspec/changes/feature-store-v1/design.md`) with unformatted embedded
  Python code fences -- out of scope for this change, left as-is.
- [x] 7.2 Counts recorded, all green: `packages/mlb-research/tests/test_backtest.py`
  — 12 passed. `tests/unit/test_experiment_metrics.py` — 48 passed.
  `tests/integration/test_experiment.py` +
  `tests/integration/test_feature_select.py` +
  `tests/integration/test_feature_select_stepwise.py` — 39 passed (real
  PostgreSQL). `packages/mlb-research/tests/` as a whole — 43 passed. Full
  `tests/unit/` — 1226 passed. No failures, no skips, no xfails.
- [x] 7.3 Both pass: `mlb_research.backtest` import does not pull in
  `mlb_baseball` (checked directly); a subprocess import of
  `mlb_research.backtest` has neither `sklearn` nor `xgboost` in
  `sys.modules` (same pattern as `test_module_imports_without_sklearn_or_xgboost`
  in `test_backtest.py`, run standalone here too).
- [x] 7.4 Scope audit done (`git diff --stat fd1f77b..HEAD`, this session's
  13 touched files): no migration, no `meta.*` schema change, no
  connector/conform/ingest code, no `model/elo.py` / `model/log5.py` math
  change (their functions are called, not modified, from `experiment.py`'s
  new `_estimator_factory`), no DuckDB feature store file. No `SHORTCUT:`
  markers in the diff.
- [ ] 7.5 **[OWNER]** Re-run one real experiment from the lab
  (`mlb experiment run …` against a built database) before and after, and
  confirm `meta.experiment.metrics_json` matches within the D5 tie-out
  tolerance. First confirmation at real scale that the adapter preserved the
  numbers.
