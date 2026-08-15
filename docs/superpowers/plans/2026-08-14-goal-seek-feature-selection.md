# Goal seek: feature-selection stability report (filter + embedded stages)

Goal: Implement the first two of the three stages from
`docs/superpowers/specs/2026-08-14-ml-modeling-harness-design.md` section 3
(feature selection) — the cheap permutation-importance filter and the
embedded tree-importance stage — as a new, reusable stability report on top
of the target-agnostic experiment lab landed in commit `05919ec`. Stage 3
(the forward-stepwise wrapper) is explicitly **not** part of this package;
see "Deliberate scope cut" below for why, and what it needs once this lands.

Primary outcome: `mlb experiment select-features --snapshot <id>` runs
against an existing `home_win` or `run_differential` snapshot in `mlb_test`
and produces a reproducible, persisted report of which `BASE_COLUMNS`
candidate features survive a shuffled-noise threshold, per calendar fold —
evidence, not a keep/drop decision (that's stage 3's job, later).

Safety and scope:
- Use `mlb_test` for every migration, fixture, test, and database write.
  Production `mlb` is not touched — not even read-only.
- No new runtime dependency. `sklearn.inspection.permutation_importance` is
  already part of the installed `scikit-learn==1.9.0` (verified — see Work
  Package 1). Do not add `shap`, `eli5`, or any other feature-importance
  library.
- Do not implement stage 3 (forward-stepwise wrapper) — see the scope-cut
  section. Do not touch spec sections 4-7 (Markov features, ensembles,
  neural interaction models, interoperability export) or anything about
  `run_differential`/`home_win` model behavior itself — this package only
  *reports on* candidate features, it does not change what `run()` trains on.
- Do not add a third target, and do not change `BASE_COLUMNS`,
  `TARGET_REGISTRY`, or any existing experiment-lab behavior. Read-only
  consumer of the existing snapshot/fold contract.
- Existing `home_win`/`run_differential` experiment behavior (commit
  `05919ec`) must not change in any observable way — this package only adds
  new code paths, it doesn't touch `run()`, `compare()`, `_predictions()`,
  `_probabilities()`, or any existing metric function.

Repository context (read before writing code — this is a generalization on
top of very recently landed code, not a from-scratch design):
- `mlb_baseball/model/experiment.py` at commit `05919ec` — read the whole
  file. Reuse these existing pieces directly rather than duplicating them
  (they're private/underscore-prefixed, but this new module is an
  intentional sibling extension of the same lab, not an unrelated consumer —
  import them the same way `experiment.py` itself imports from
  `mlb_baseball.model.elo`/`log5`): `TargetSpec`, `TARGET_REGISTRY`,
  `SnapshotRow`, `BASE_COLUMNS`, `DEFAULT_FOLD_YEARS`, `Fold`, `folds()`,
  `_snapshot_rows()`, `_common_rows()`, `_matrix()`, `_labels()`,
  `_make_estimator()`, `_snapshot_metadata()`, `_canonical_json()`,
  `_sha256()`. Line numbers below are from `05919ec`; if they've moved, find
  by name.
  - `_snapshot_metadata()` (line 526) — returns `(target, feature_set_version,
    source_profile)` for a snapshot; use this to discover which target a
    snapshot was declared for, exactly like `run()` (line 849) does. The CLI
    for this package takes only `--snapshot`, not a separate `--target` —
    the snapshot already declares it, a redundant flag risks a
    caller-supplied mismatch `run()` doesn't have to guard against today.
  - `_make_estimator("logistic", ...)`/`_make_estimator("ridge", ...)` (line
    445) already build the exact `Pipeline([impute, scale, model])` this
    package's filter stage needs for `home_win`/`run_differential`
    respectively — reuse them, don't rebuild.
  - `_matrix()` (line 427) builds a `(n_rows, len(BASE_COLUMNS))` array from
    `BASE_COLUMNS` only (not `LOG5_COLUMNS`) — confirmed by reading it.
    `BASE_COLUMNS` (11 columns, line 46) is this package's entire candidate
    pool. It's small today; the filter-first architecture exists so this
    scales once Plan 03 lands more `gold.game_feature` families, per the
    design spec — don't skip building it just because 11 is a small number
    right now.
  - `run()` (line 849) shows the exact chronological training-row slice this
    package must reuse identically: `[row for row in eligible if row.season
    <= fold.train_through_season]`. Do not write a second, slightly
    different version of this filter.
- **Two facts verified directly against the installed environment during
  design — do not re-derive, use them as given:**
  1. `HistGradientBoostingClassifier`/`Regressor` do **not** expose
     `.feature_importances_`, even after fitting (confirmed: `hasattr()` is
     `False` post-`.fit()` on this installed `scikit-learn==1.9.0`). Use
     `xgb.XGBClassifier`/`XGBRegressor` for the embedded stage instead — they
     do expose it, and are already available via `_make_estimator("xgboost",
     ...)`/`_make_estimator("xgboost_regressor", ...)`.
  2. On this installed `xgboost==3.3.0`, `XGBClassifier().importance_type` is
     `None` by default, which resolves to gain-based importance internally
     for `.feature_importances_` — confirmed by fitting a toy model and
     reading `.feature_importances_` directly (values summed to 1.0, ranked
     the truly-informative synthetic column far above the noise columns, as
     expected of gain-based importance). Record this exact finding (verified
     against the installed version) in the ADR — don't assert a default from
     memory, and don't assume a future xgboost upgrade keeps it.
- `docs/superpowers/specs/2026-08-14-ml-modeling-harness-design.md` section 3
  — the design this prompt implements a scoped slice of.
- `migrations/0053_experiment_target_registry.sql` and `docs/DECISIONS.md`
  ADR-064 — the pattern for adding a `meta.*` table plus recording the
  design decisions and corrections found while building it; this package's
  Work Package 4 follows the same shape.

Deliberate scope cut — why stage 3 isn't in this package:

The design spec's stage 3 (forward-stepwise wrapper, nested walk-forward
validated one step at a time) needs its own nested-CV mechanics inside each
outer fold's training window, which is meaningfully more complex and more
leakage-prone to get right than stages 1-2. Landing stages 1-2 first gives
stage 3 something real and already-tested to build on (the stage-1 survivor
set it's supposed to run on), mirrors the design spec's own "Implementation
sequencing" note about staging later work, and matches how the previous
package (target-agnostic framework) was itself carved out of a larger spec
rather than attempted whole. Do not attempt stage 3 in this package even if
it looks tempting once stages 1-2 are working — say so explicitly in the
final report and recommend it as the next goal-seek package instead.

---

Work package 1 — New module skeleton and verified environment facts:

- Create `mlb_baseball/model/feature_select.py`. Module docstring should
  state plainly what it does and doesn't do: computes a per-fold,
  per-candidate-feature stability report (filter + embedded stages only);
  does not select or promote features, does not change what any model
  trains on, does not implement the stepwise wrapper.
- Confirm for yourself, don't just trust this prompt, that
  `sklearn.inspection.permutation_importance` imports cleanly and that
  `get_scorer_names()` includes `"neg_log_loss"` and
  `"neg_mean_absolute_error"` in this project's installed environment
  (`uv run python -c "..."`) before writing code against them.

Work package 2 — Migration and persistence:

- Add `migrations/0054_feature_selection.sql`: `meta.feature_selection`
  table — `selection_id text primary key`, `snapshot_id text not null
  references meta.experiment_snapshot(snapshot_id)`, `target text not null
  references meta.experiment_target(name)`, `fold_plan_json jsonb not null`,
  `method_config_json jsonb not null` (record `n_repeats`, `seed`,
  `noise_column` name, which estimator each stage used), `status text not
  null check (status in ('running', 'success', 'failed'))`, `error text`,
  `result_json jsonb`, `artifact_uri text`, `artifact_sha256 text`,
  `started_at timestamptz not null default now()`, `finished_at
  timestamptz`. One row per selection run — this report isn't naturally
  per-fold the way `meta.experiment_fold` is (a fold produces one row of the
  *same* stability report, not an independent scored result), so a single
  table is enough; don't copy the two-table `experiment`/`experiment_fold`
  split unless you find a concrete reason to during implementation, and
  explain that reason in the ADR if you do.
- Write a small content-addressed artifact writer for the JSON report,
  following `_write_artifact()`'s pattern (line 797) but adapted — one
  artifact per `selection_id`, not per fold, written to
  `artifacts/feature_selection/` (mirroring `artifacts/experiments/`).

Work package 3 — The selection algorithm:

- `select_features(conn, snapshot_id, *, n_repeats=30, seed=0, fold_years=DEFAULT_FOLD_YEARS, artifact_dir=Path("artifacts/feature_selection")) -> dict`:
  1. `target, feature_set_version, _ = _snapshot_metadata(conn, snapshot_id)`;
     look up `spec = TARGET_REGISTRY[target]`.
  2. `all_rows = _snapshot_rows(conn, snapshot_id)`; `eligible =
     _common_rows(all_rows, spec)` — identical eligibility filtering to
     `run()`, reused, not reimplemented.
  3. Compute a deterministic `selection_id` the same way
     `_experiment_id()` does (line 782) — hash `{snapshot_id, target,
     fold_plan, n_repeats, seed}` — and check `meta.feature_selection` for an
     existing successful row first (same reuse-not-rerun behavior `run()`
     has at line ~858-875). This is a read-heavy, potentially slow
     computation (2 model fits × `n_repeats` permutations × 9 folds); don't
     make a caller pay for it twice on the same inputs.
  4. For each `fold in folds(fold_years)`: `train_rows = [row for row in
     eligible if row.season <= fold.train_through_season]` (identical slice
     to `run()`). If a fold has too few training rows to fit meaningfully
     (reuse `run()`'s existing bare `if not train_rows` check as the floor —
     don't invent a new arbitrary minimum without evidence), record it as
     skipped in that fold's result rather than crashing the whole selection.
  5. Build the augmented matrix: `base_matrix = _matrix(train_rows)` (shape
     `(n, 11)`), then append one synthetic noise column: `rng =
     np.random.default_rng(seed + fold.test_season)`; `noise =
     rng.standard_normal(len(train_rows))`; `augmented = np.column_stack([base_matrix, noise])`.
     Column name list = `list(BASE_COLUMNS) + ["__noise__"]`.
  6. `labels = _labels(train_rows, spec)`.
  7. **Stage 1 (filter):** fit `_make_estimator("logistic", {}, seed)` for
     `home_win` / `_make_estimator("ridge", {}, seed)` for
     `run_differential` on `(augmented, labels)`. Run
     `permutation_importance(estimator, augmented, labels, scoring="neg_log_loss"
     if spec.task_type == "classification" else "neg_mean_absolute_error",
     n_repeats=n_repeats, random_state=seed + fold.test_season)`. Read
     `.importances_mean` — a feature "survives stage 1 in this fold" if its
     mean importance is strictly greater than the `__noise__` column's mean
     importance in the same run. This is the noise threshold the design
     spec calls for — not an arbitrary epsilon, an actually-injected control
     column measured in the same fit.
  8. **Stage 2 (embedded):** fit `_make_estimator("xgboost", {}, seed)` /
     `_make_estimator("xgboost_regressor", {}, seed)` directly on
     `(augmented, labels)` — no imputer needed, XGBoost handles the same
     NaN-as-missing values these matrices already carry, same as the
     existing `run()` path does for these two families. Read
     `.feature_importances_`; a feature "survives stage 2 in this fold" if
     its importance is strictly greater than `__noise__`'s.
  9. Record per-fold: which of the 11 `BASE_COLUMNS` survived stage 1, which
     survived stage 2, which survived both.
  10. After all folds: build the stability report — for each of the 11
      features, `stage1_survived_folds` (count out of however many folds
      actually ran), `stage2_survived_folds`, `both_stages_survived_folds`,
      and the raw per-fold booleans (don't collapse to just the counts — a
      future reader needs to see *which* eras a feature was fragile in, not
      just how many). Do not compute a keep/drop verdict — this package
      reports evidence, stage 3 (later) makes the decision.
  11. Persist to `meta.feature_selection` and the JSON artifact; return the
      report dict.

Work package 4 — CLI and docs:

- Add `select-features` under the `experiment` subcommand
  (`mlb_baseball/cli.py`), taking only `--snapshot` (see Repository Context
  for why no separate `--target`). Print a simple per-feature table:
  feature name, `stage1: k/n`, `stage2: k/n`, `both: k/n`.
- `docs/EXPERIMENT_RUNBOOK.md`: document the new command, what it reports,
  and explicitly that it does not select or drop anything — that's future
  work.
- `docs/DECISIONS.md`: new ADR recording the design (why filter+embedded
  only, stage 3 deferred and why), the two verified environment facts from
  Work Package 1's repository context (HGB lacking `feature_importances_`,
  XGBoost's default `importance_type` behavior on this installed version),
  and any other real finding made during implementation.
- `docs/TABLE_CONTRACTS.md`: add `meta.feature_selection`.
- `plans/04-modeling-simulation-and-experiments.md`: update 04E's status.
- `plans/PROGRESS.md`: dated entry.

Work package 5 — Tests:

- Unit (`tests/unit/`): a synthetic-data test that doesn't touch the
  database — build a matrix where one column is a genuinely informative
  linear function of the label plus noise, and 2-3 columns are pure random
  noise; confirm the informative column's stage-1 and stage-2 importances
  reliably exceed an injected `__noise__` column's, and the genuinely-noise
  columns don't reliably (run it across a few different seeds and assert
  the informative column wins in the large majority, not literally every
  single seed — permutation importance has real sampling variance, don't
  write a flaky test that assumes zero variance). Also unit-test the
  `selection_id` determinism (same inputs → same id, reused not rerun).
- Integration (`tests/integration/`, against `mlb_test` only): end-to-end
  `select_features()` against a real `home_win` snapshot and a real
  `run_differential` snapshot from the existing rehearsal fixtures, proving
  idempotency (same `selection_id`, no duplicate `meta.feature_selection`
  row on rerun) and that the CLI command runs and prints without error.

Work package 6 — Close-out:

- Run the full test suite, Ruff, and mypy; fix anything until clean.
- Commit in coherent steps and push to `main` directly, per this repo's
  established direct-to-main workflow (`CLAUDE.md`).

Definition of done:
- `mlb experiment select-features --snapshot <id>` works against both a real
  `home_win` and a real `run_differential` snapshot in `mlb_test`.
- The two verified-environment facts (HGB importance gap, XGBoost import
  type) are recorded in the ADR with how they were confirmed, not asserted
  from memory.
- Stage 3 was not attempted; the final report says so explicitly and
  recommends it as the next goal-seek package.
- No change to `run()`, `compare()`, or any existing experiment-lab
  behavior — this is purely additive.
- No production `mlb` read or write occurred. No new runtime dependency.
- Full pytest suite, Ruff, and mypy pass clean.
- Docs listed in Work Package 4 updated in the same change as the code.
- Commits pushed to `main`.
- End with: changed files, exact test results, the synthetic-test evidence
  that the algorithm actually separates a known-informative column from
  known noise (not just "tests passed" — show the actual survival counts),
  and a specific recommendation for stage 3's design given what this
  package learned.
