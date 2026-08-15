# Goal seek: target-agnostic experiment lab + run_differential

Goal: Implement sections 1-2 of
`docs/superpowers/specs/2026-08-14-ml-modeling-harness-design.md` — generalize
`mlb_baseball/model/experiment.py` from a hardcoded `home_win` classification
lab into a small target registry that can also run `run_differential`
(regression), on the exact same `game_base_v1` feature family and the exact
same chronological-fold discipline. Read the full spec before starting; this
prompt is the actionable slice of it, not a replacement for it.

Primary outcome: `mlb experiment snapshot --target run_differential`,
`mlb experiment run --target run_differential --model <regressor>`, and
`mlb experiment compare --snapshot <id>` all work end to end in `mlb_test`,
alongside `home_win` behaving byte-for-byte as it does today (regression-proof
this, don't just claim it).

Safety and scope:
- Use `mlb_test` for every migration, fixture, test, and database write.
  Production `mlb` is not touched at all in this package — not even
  read-only. `tests/conftest.py::_assert_test_database_url` already enforces
  this; do not weaken it.
- No new runtime dependency. Ridge regression is already in scikit-learn
  (`sklearn.linear_model.Ridge`); `HistGradientBoostingRegressor` is already
  in `sklearn.ensemble`; `xgb.XGBRegressor` is already available from the
  `xgboost` package already imported in `experiment.py`. Do not add MLflow,
  Optuna, LightGBM, PyTorch, or anything else — `docs/EXPERIMENT_RUNBOOK.md`
  is explicit that those remain deferred until a small contract like this one
  demonstrates real need, and this package doesn't change that.
- Do not touch feature selection (spec section 3), ensembles/stacking (section
  5), Markov-derived features (section 4, blocked on Plan 04D not existing
  yet), neural interaction models (section 6), or the Parquet/interoperability
  export (section 7). All five are designed in the spec on purpose so their
  integration points are already decided, but none of them is this package's
  job. Resist the temptation to start any of them "since you're in there."
- Do not add a third target. `home_win` and `run_differential` are the two
  rows this package seeds into the new target registry — nothing else.
- Do not wire anything from this package into production prediction. This
  remains a research/rehearsal lab, exactly as `docs/EXPERIMENT_RUNBOOK.md`
  already states about the existing `home_win` lab.
- `home_win`'s existing behavior must not change in any observable way:
  same snapshot IDs for the same underlying rows, same metrics for the same
  experiment config. Prove this with a regression test, not by inspection.

Repository context (read these before writing code — this is not a from-
scratch design, it's a generalization of working code):
- `mlb_baseball/model/experiment.py` — the whole lab. Read the entire file;
  it's ~830 lines and every function below is referenced by exact line
  numbers from the version at commit `addc592`. If lines have moved, find the
  function by name instead of trusting the line number blindly.
- `migrations/0047_experiment_lab.sql`, `0048_experiment_aggregate_metrics.sql`,
  `0049_immutable_experiment_snapshots.sql` — the current schema, including
  the two `CHECK (target = 'home_win')` constraints this package removes.
- `docs/EXPERIMENT_RUNBOOK.md` — the user-facing contract for this lab; update
  it in the same change once the CLI actually supports a second target.
- `docs/superpowers/specs/2026-08-14-ml-modeling-harness-design.md` sections
  1-2 — the design this prompt implements. If anything here conflicts with
  that spec, this prompt is the corrected, more-specific version (see the two
  corrections called out explicitly in Work Package 3) — note the correction
  in your final report rather than silently picking one.
- `mlb_baseball/sql/game_feature_rebuild.sql` lines ~95-140 — confirms exactly
  which columns already exist in `gold.game_feature` and how they're computed
  (`home_pyth_wpct`/`away_pyth_wpct`, `home_run_diff`/`away_run_diff`,
  `home_runs_for`/`home_runs_allowed`/etc.). Read this before adding any new
  baseline — the run-environment columns this package needs already exist and
  already flow into `experiment.py::BASE_COLUMNS`; you should not need a new
  migration on `gold.game_feature` itself, only on the `meta.experiment*`
  tables.
- `docs/RESEARCH.md` "Pythagorean expectation" section — cited in this
  prompt's Work Package 3 correction; read it before deciding what the
  regression baselines actually are.

---

Work package 1 — Target registry and the row_sha256 uniqueness bug:

- Add a migration (next number after `0049`) creating `meta.experiment_target
  (name text primary key, task_type text not null check (task_type in
  ('classification', 'regression')), description text not null)`, seeded with
  exactly two rows: `home_win` / `classification` and `run_differential` /
  `regression`.
- Replace both `CHECK (target = 'home_win')` constraints
  (`meta.experiment_snapshot.target`, `meta.experiment.target`) with a foreign
  key to `meta.experiment_target(name)`.
- **Required correctness fix, found by reading the code, not optional
  polish:** `meta.experiment_snapshot.row_sha256` currently has a bare
  `UNIQUE` constraint (`migrations/0047_experiment_lab.sql`), and
  `create_snapshot()` (`experiment.py:218-256`) looks up an existing snapshot
  with `SELECT snapshot_id FROM meta.experiment_snapshot WHERE row_sha256 =
  %s` (line 226) — no `target` filter. `_row_identity()` (line 197-215) hashes
  row content that does not include which target the snapshot was created
  for. Once a second target exists, a `run_differential` snapshot built from
  the same underlying rows as an existing `home_win` snapshot will hash to
  the same `row_sha256`, and the current lookup will silently return the
  wrong snapshot's ID (or the INSERT will fail on the UNIQUE constraint,
  depending on which happens first). Fix both: change the constraint to
  `UNIQUE (row_sha256, target)`, and change the lookup query to
  `WHERE row_sha256 = %s AND target = %s`. Write a regression test that
  creates a `home_win` snapshot and a `run_differential` snapshot from
  identical underlying rows and asserts they get two different snapshot IDs,
  each independently reusable on a second call with the same target.
- Add a frozen `TargetSpec` dataclass to `experiment.py`: `name: str`,
  `task_type: Literal["classification", "regression"]`, `label: Callable[[SnapshotRow], float]`,
  `required_columns: tuple[str, ...]` (see Work Package 2), `valid_model_families: tuple[str, ...]`.
  Build a `TARGET_REGISTRY: dict[str, TargetSpec]` with the two entries.
  `home_win`'s spec must reproduce today's exact behavior: `label=lambda row:
  float(row.home_win)`, `required_columns=("home_win_pct", "away_win_pct")`
  (matches today's `_common_rows`, see Work Package 2),
  `valid_model_families=("home_rate", "log5", "elo", "logistic",
  "hist_gradient_boosting", "xgboost")` (today's `SUPPORTED_MODELS` tuple,
  unchanged).

Work package 2 — Thread target through snapshot creation and common-row
filtering:

- `create_snapshot()` gains a `target: str = "home_win"` parameter (keeps the
  existing default so any caller that doesn't pass one keeps today's
  behavior). Validate it against `TARGET_REGISTRY` and raise `ExperimentError`
  for anything else. Use it instead of the module-level `TARGET` constant at
  both use sites (line 222 snapshot_id construction, line 244 the INSERT).
  The row-selection SQL and the copied row payload do **not** change per
  target — `SnapshotRow` already carries `home_score`/`away_score`/`home_win`
  unconditionally (confirmed by reading `_source_rows`, lines 133-194), so
  every target reads its label out of the same stored row. Only the declared
  `target` bookkeeping value changes.
- `_common_rows()` (line 342-350) currently hardcodes the Log5-driven
  `home_win_pct`/`away_win_pct` non-null filter. Make it take a `TargetSpec`
  and filter on `spec.required_columns` generically:
  `all(row.values[column] is not None for column in spec.required_columns)`.
  For `home_win`, `required_columns=("home_win_pct", "away_win_pct")`
  reproduces today's exact filter — write the regression test from the
  package-level safety note to prove this line-for-line.
  For `run_differential`, `required_columns=("home_runs_for",
  "home_runs_allowed", "away_runs_for", "away_runs_allowed", "home_wins",
  "home_losses", "away_wins", "away_losses")` — these are the columns the
  season-average baseline in Work Package 3 needs. **Before finalizing this
  list, write a fixture test using a genuine first-game-of-season row and
  confirm empirically whether these columns are NULL or 0 at that point** —
  do not assume; `sum()` over an empty Postgres window frame returns NULL
  while `count()` returns 0, and `home_wins`/`home_losses` come from `count()`
  while `home_runs_for`/`home_runs_allowed` come from `sum()`
  (`game_feature_rebuild.sql`'s `running` CTE) — they may not be null
  together. Document what you actually find in the ADR from Work Package 7.

Work package 3 — Regression target, baselines, and models (with two
corrections to the design spec, found while reading the actual SQL):

- **Correction 1 (drop the "Pythagenpat baseline" for `run_differential` as
  originally described in the spec):** the spec's section 2 describes a
  "Pythagenpat-derived expected differential" baseline. `home_pyth_wpct`
  (`game_feature_rebuild.sql` lines 108-118) is Pythagenpat's *win
  probability* output — there is no standard, sourced formula converting a
  Pythagorean win-probability estimate directly into an expected run
  differential (searched `docs/RESEARCH.md`'s existing Pythagorean citations
  during the design session; none supply one). Inventing an unsourced
  conversion formula would repeat the exact mistake `docs/RESEARCH.md`'s
  log5 section already documents and corrected (an unvalidated formula
  shipped as if sourced). Do not add a Pythagenpat-labeled baseline for this
  target. If you want it anyway, you must find and cite a real source for
  the win%-to-run-differential conversion first and record that citation in
  the ADR — absent that, skip it and say explicitly in the ADR that it was
  considered and dropped for this reason.
- **Correction 2 (the real second baseline, already computable from existing
  columns, no new SQL/migration needed):** `gold.game_feature` already has
  `home_run_diff`/`away_run_diff` (season-to-date entering run differential,
  same `game_feature_rebuild.sql` CTE) but they are **not** currently in
  `experiment.py::BASE_COLUMNS`/`ALL_COLUMNS`. You do not need to add them:
  the same value is already derivable from columns already in `BASE_COLUMNS`
  — `home_runs_for - home_runs_allowed` divided by `home_wins + home_losses`
  (games played), same for away. Implement the season-average baseline this
  way in Python (`_predictions` for regression, see below), guarding
  divide-by-zero per what Work Package 2's fixture test found.
- Baselines for `run_differential`, both required before any ML regressor is
  scored (mirrors the existing rule that Log5/Elo stand up before
  `logistic`/`hist_gradient_boosting`/`xgboost` for `home_win`):
  1. `zero` — predicts `0.0` for every row, no parameters.
  2. `season_average` — the derived value from Correction 2, no parameters.
- ML model families for `run_differential`, named distinctly from their
  classification counterparts (do not overload `"hist_gradient_boosting"` —
  keep `model_family` alone sufficient to know which estimator class runs,
  without also having to look up the target): `ridge` (`sklearn.linear_model.Ridge`),
  `hist_gradient_boosting_regressor` (`sklearn.ensemble.HistGradientBoostingRegressor`),
  `xgboost_regressor` (`xgb.XGBRegressor`). Add these four names (plus the two
  baselines) as `run_differential`'s `valid_model_families` in its
  `TargetSpec`.
- Extend `_make_estimator` with these three new branches, following the exact
  existing pattern (median imputation + missing indicator, same as
  `logistic`/`hist_gradient_boosting` — see lines 367-393): `ridge` gets the
  same `Pipeline([impute, scale, Ridge(random_state=seed, **parameters)])`
  shape as `logistic`; `hist_gradient_boosting_regressor` mirrors
  `hist_gradient_boosting`'s `Pipeline([impute,
  HistGradientBoostingRegressor(random_state=seed, **parameters)])`;
  `xgboost_regressor` mirrors the plain `xgb.XGBRegressor(...)`
  instantiation `xgboost` uses today, same default hyperparameters
  (`n_estimators=100, max_depth=3, learning_rate=0.05`), with
  `eval_metric="rmse"` instead of `"logloss"`.
- Extend `_validate_parameters` (lines 396-412) with matching branches for the
  four new names — `zero`/`season_average` accept no parameters (same as
  `home_rate`/`log5`/`elo`); `ridge`/`hist_gradient_boosting_regressor`/
  `xgboost_regressor` validate against `Ridge().get_params(deep=False)` /
  `HistGradientBoostingRegressor().get_params(deep=False)` /
  `xgb.XGBRegressor().get_params(deep=False)` respectively.
- `_labels` (line 363-364) becomes `_labels(rows, spec)`, calling
  `spec.label(row)` instead of hardcoding `int(row.home_win)`. `_matrix`
  (line 353-360) is unchanged — both targets train on the same
  `BASE_COLUMNS` feature matrix, only the label differs. State this
  explicitly in the ADR: it's the concrete proof that this generalization
  didn't require duplicating the feature layer.
- Add `_predictions()` as the regression sibling of `_probabilities()` (lines
  486-513): same signature shape, dispatches `zero`/`season_average` inline
  (no estimator, matching how `home_rate`/`log5` are handled today), then
  falls through to `_make_estimator(...).fit(...).predict(...)` for the three
  ML families (note: `.predict`, not `.predict_proba` — regressors don't have
  the latter).

Work package 4 — Regression metrics:

- Add `_regression_metrics(y, predictions, seed)` alongside the existing
  `_metrics` (do not merge them — the existing classification path is
  reviewed, working code; branching inside one function to handle two
  unrelated metric shapes makes it harder to read, not easier). Primary:
  `mae` (`sklearn.metrics.mean_absolute_error`), `rmse` (`root_mean_squared_error`
  if your installed scikit-learn version has it, else
  `mean_squared_error(..., squared=False)` — check the installed version in
  `pyproject.toml`/`uv.lock` before picking which). Add the same seeded
  bootstrap-resampling 95% CI pattern the existing `_metrics` already does for
  `log_loss_95ci`/`brier_95ci` (lines 561-575) — `mae_95ci`, `rmse_95ci`, same
  200-resample, same `Random(seed)` determinism.
- Add a residual-calibration report as the regression analog of
  `_calibration` (lines 516-543): bin games by **predicted-value decile**
  (data-driven bin edges via `np.quantile`, not fixed `[0,1]` bins — run
  differential isn't bounded), report each bin's row count, mean prediction,
  and mean residual (`actual - predicted`). A well-calibrated model has
  near-zero mean residual in every bin, not just a low aggregate MAE — say
  this in the docstring, matching how `_calibration`'s existing intent is
  documented.
- `_aggregate_metrics` (lines 606-624) is classification-specific
  (log_loss/brier/accuracy weighted average). Add
  `_aggregate_regression_metrics` alongside it (mae/rmse weighted average,
  same row-weighting shape) rather than branching the existing one.

Work package 5 — Wire target dispatch through `run()`/`compare()`/CLI:

- `run()` (lines 627-808): replace the hardcoded `if config.target != TARGET`
  check (line 631-632) with `if config.target not in TARGET_REGISTRY: raise
  ExperimentError(...)`, then look up the `TargetSpec` and use it for: model
  family validation (`config.model_family not in spec.valid_model_families`,
  replacing the flat `SUPPORTED_MODELS` check at line 629-630), `_labels`,
  `_common_rows`, and dispatching to `_probabilities`/`_metrics`/
  `_aggregate_metrics` for `classification` vs. `_predictions`/
  `_regression_metrics`/`_aggregate_regression_metrics` for `regression`. The
  predictions payload written to the fold artifact (lines 719-726,
  `"actual_home_win"` key) needs a target-aware key name too — don't silently
  keep writing a field called `actual_home_win` for a `run_differential`
  experiment's artifact.
- `compare()` (lines 811-825) needs no structural change — it already just
  echoes back whatever `metrics_json` each fold stored, so it reports
  whichever metric set the target produced automatically. Verify this with a
  test rather than assuming.
- CLI (`mlb_baseball/cli.py`, the `experiment` subparsers block): add
  `--target` to `experiment snapshot` (default `"home_win"`) and to
  `experiment run` (default `"home_win"`, `choices` should be
  `list(experiment.TARGET_REGISTRY)`). `experiment run --model` choices need
  to come from the union of every target's `valid_model_families` at
  argparse-definition time (argparse can't validate against the `--target`
  value dynamically at parse time) — do the real per-target validation inside
  `run()` (already covered above) and let argparse only reject completely
  unknown model names.

Work package 6 — Tests:

- Unit (`tests/unit/`): `TargetSpec` registry lookup/validation; regression
  metric functions against **hand-computed** MAE/RMSE fixtures (pick simple
  numbers you can check by hand, e.g. predictions `[1, 2, 3]` vs actuals
  `[1, 4, 3]` → MAE = 1.0, not a copy of sklearn's own test fixtures); the new
  `row_sha256`/target uniqueness fix from Work Package 1.
- Integration (`tests/integration/`, against `mlb_test` only):
  - Full regression proof that `home_win` behavior is byte-for-byte unchanged
    post-refactor: same snapshot ID for the same rows, same metrics for the
    same `ExperimentConfig`, run both before-and-after your changes if
    practical (or construct the assertion from known-good recorded output).
  - End-to-end `run_differential` experiment: snapshot → run (at least the
    `zero` baseline and one ML regressor) → compare, on a small real sample,
    proving idempotency (re-running `experiment run` with the same config
    returns the same `experiment_id` and doesn't duplicate fold rows — same
    idempotency rule this project requires everywhere, see CLAUDE.md
    "Definition of done" item 3).
  - The first-game-of-season null/zero fixture from Work Package 2.
  - A fixture proving `_common_rows` correctly filters `run_differential`'s
    `required_columns` and correctly still filters `home_win`'s as before.

Work package 7 — Docs and close-out:

- `docs/EXPERIMENT_RUNBOOK.md`: document the `--target` flag, the two
  `run_differential` baselines and three model families, and the residual-
  calibration report — following that doc's existing terse style.
- `docs/DECISIONS.md`: new ADR documenting (a) the target-registry design and
  why `home_win`'s behavior is provably unchanged, (b) the `row_sha256`
  uniqueness fix and why it was necessary, (c) the two corrections from Work
  Package 3 (Pythagenpat baseline dropped, why; season-average baseline
  formula used instead), (d) whatever Work Package 2's first-game-of-season
  fixture actually found.
- `docs/TABLE_CONTRACTS.md`: add `meta.experiment_target` to the meta-schema
  table list.
- `plans/04-modeling-simulation-and-experiments.md`: update the top status
  line — this package is 04B work (target ladder), still `mlb_test` only, no
  promotion, no production write, matching the existing status line's
  posture.
- `plans/PROGRESS.md`: dated entry, same evidence-log style as existing
  entries — what landed, what test counts passed, what was explicitly
  deferred.
- Run the full test suite, Ruff, and mypy; fix anything until clean.
- Commit in coherent steps (one work package per commit, or combine adjacent
  ones — your judgment) and push to `main` directly, per this repo's
  established direct-to-main workflow (`CLAUDE.md`).

Definition of done:
- `mlb experiment snapshot --target run_differential`,
  `mlb experiment run --target run_differential --model <name>` (for each of
  `zero`, `season_average`, `ridge`, `hist_gradient_boosting_regressor`,
  `xgboost_regressor`), and `mlb experiment compare` all work against
  `mlb_test`.
- `home_win`'s existing behavior is proven unchanged by a regression test,
  not just asserted.
- The `row_sha256` uniqueness bug is fixed and covered by a test that would
  have failed before the fix.
- Both spec corrections (Pythagenpat baseline dropped or properly sourced;
  season-average baseline implemented from existing columns) are recorded in
  the ADR, not silently decided.
- No code from spec sections 3-7 was started.
- No production `mlb` read or write occurred.
- Full pytest suite, Ruff, and mypy pass clean.
- Docs listed in Work Package 7 are updated in the same change as the code.
- Commits pushed to `main`.
- End with: changed files, exact test results, the first-game-of-season null/
  zero finding from Work Package 2, and a specific recommendation for what
  comes next (likely: spec section 3's feature-selection package, or waiting
  for Plan 04D before section 4).
