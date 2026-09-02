# Goal seek: forward-stepwise wrapper (feature-selection stage 3)

Goal: Implement stage 3 of `docs/superpowers/specs/2026-08-14-ml-modeling-harness-design.md`
section 3 — the forward-stepwise wrapper — on top of the filter+embedded
stability report landed in commit `442f47e`
(`mlb_baseball/model/feature_select.py`). This is the piece that was
deliberately cut from that package because it needs correct nested
chronological validation to avoid leakage; that correctness is this
package's entire job, not a detail to get to eventually.

Primary outcome: `mlb experiment select-features-stepwise --snapshot <id>`
runs against an existing `home_win` or `run_differential` snapshot in
`mlb_test`, derives its candidate set from the already-persisted stage-1/2
stability report, and reports which of those candidates a nested
walk-forward stepwise search would add — evidence again, not an automatic
promotion, matching the posture of both prior packages.

Safety and scope:
- Use `mlb_test` for every migration, fixture, test, and database write.
  Production `mlb` is not touched — not even read-only.
- No new runtime dependency. This package needs nothing beyond what's
  already used by `_make_estimator("logistic"/"ridge", ...)` and plain
  numpy — it does **not** need `sklearn.inspection.permutation_importance`
  (that was stages 1-2's tool; stage 3 uses a different, paired
  real-vs-shuffled comparison, described below).
- Do not touch `run()`, `compare()`, `_predictions()`, `_probabilities()`,
  or `select_features()` (stages 1-2) — this package only reads the
  stage-1/2 result, it doesn't change how that result is computed.
- Do not touch spec sections 4-7 (Markov features, ensembles, neural
  interaction models, interoperability export).
- This package produces evidence, exactly like stages 1-2. It must not
  change what any model actually trains on, and must not silently promote
  or auto-apply a feature set anywhere.

Repository context (read before writing code):
- `mlb_baseball/model/feature_select.py` (commit `442f47e`) — read the whole
  file. Reuse `_selection_id`'s pattern (adapt, don't duplicate blindly),
  `_write_selection_artifact`, and the `TARGET_REGISTRY`/`_snapshot_metadata`/
  `_snapshot_rows`/`_common_rows`/`folds`/`_make_estimator`/`_labels` imports
  it already has from `mlb_baseball.model.experiment`. `select_features()`
  (line 66) is idempotent and reusable — call it directly to get the
  stage-1/2 stability report rather than re-deriving it or querying
  `meta.feature_selection` yourself.
- `docs/DECISIONS.md` ADR-065 — its own "Recommendation for Stage 3's
  Design" section already proposed the shape this package should follow:
  candidate set = features surviving *both* stage 1 and stage 2 in at least
  70% of evaluated folds; inner chronological split = train on seasons
  ≤ T-2, validate on season T-1, inside each outer fold's training window
  (which itself trains on seasons ≤ T-1 and tests on season T). Adopt this
  as the base design — the sections below fill in what it didn't fully
  specify (exact scoring, threshold mechanics, seeding, and the empty-data
  edge case).
- **Verified directly against the existing test fixture, not assumed —
  read `tests/integration/test_experiment.py`'s `_seed()` (around line 30)
  yourself to confirm:** it seeds seasons 2015 (8 games), 2016 (8 games),
  2017 (8 games), and 2018 (1 game). For the outer fold `season-2016`
  (`train_through_season=2015`), an inner split needing `season <= 2014`
  for inner-train has **no data at all** in this fixture — this is a real,
  expected case your code must handle gracefully (skip, don't crash), not a
  fixture bug to work around. For `season-2017` (`train_through_season=2016`)
  and `season-2018` (`train_through_season=2017`), both inner-train and
  inner-validate have real rows. Your integration test should use
  `fold_years=(2016, 2017, 2018)` specifically so it exercises both the
  skip path and the genuine nested-split path against this existing
  fixture — you should not need to extend or add a new fixture for this
  package.

Work package 1 — Candidate-set derivation:

- Add `select_features_stepwise(conn, snapshot_id, *, seed=0, fold_years=DEFAULT_FOLD_YEARS, min_survival_fraction=0.70, artifact_dir=Path("artifacts/feature_selection_stepwise")) -> dict`
  to `mlb_baseball/model/feature_select.py` (or a new sibling module — see
  the note at the end of Work Package 2 about file size).
- Call the existing `select_features(conn, snapshot_id, fold_years=fold_years,
  seed=seed)` first (reused if already computed — it's idempotent) to get
  the stage-1/2 stability report.
- Derive the candidate set: features where `both_stages_survived_folds /
  total_folds_evaluated >= min_survival_fraction`. If this set is empty,
  raise `ExperimentError` with a clear message ("no candidate features
  survived stage 1+2 at the Nth-percent threshold; nothing to search over")
  rather than silently doing nothing or falling back to the full
  `BASE_COLUMNS` set — a silent fallback would defeat the point of having
  run stages 1-2 first.

Work package 2 — The nested stepwise search:

- For each `fold in folds(fold_years)` (the same outer folds `run()` and
  `select_features()` use):
  1. `outer_train_rows = [row for row in eligible if row.season <=
     fold.train_through_season]` — identical slice to every other place in
     this codebase that does this; import `eligible` the same way
     `select_features()` does (`_common_rows(_snapshot_rows(conn,
     snapshot_id), spec)`).
  2. Inner split: `inner_train_rows = [row for row in outer_train_rows if
     row.season <= fold.train_through_season - 1]`,
     `inner_validate_rows = [row for row in outer_train_rows if row.season
     == fold.train_through_season]`. (Note: `fold.train_through_season` is
     already "T-1" relative to the outer test season T, so the inner
     validate season is literally `fold.train_through_season` itself — read
     `Fold`'s definition in `experiment.py` to confirm this indexing before
     coding, don't just trust this prompt's arithmetic blindly.)
  3. If either `inner_train_rows` or `inner_validate_rows` is empty, record
     this fold as `{"skipped": True, "reason": "insufficient inner-split
     data"}` in the results and move to the next fold — this is the exact
     case the `season-2016` fold in the test fixture exercises.
  4. Build a small helper (new, since `_matrix()` hardcodes the full
     `BASE_COLUMNS` order and this package needs arbitrary named subsets):
     `_named_matrix(rows, feature_names) -> np.ndarray`, pulling
     `row.values[name]` for each row/name pair — `SnapshotRow.values` is
     already a dict keyed by column name, this is a direct lookup, not a
     new data source.
  5. Run forward selection: start with `selected: list[str] = []` and
     `remaining = list(candidates)` (candidates from Work Package 1, in
     `BASE_COLUMNS` order for determinism). Loop:
     - For each `candidate in remaining`: fit the target's baseline probe
       model (`_make_estimator("logistic", {}, seed)` for `home_win`,
       `_make_estimator("ridge", {}, seed)` for `run_differential` — same
       cheap-baseline choice stage 1 already established, reused here for
       methodological consistency and speed) on
       `_named_matrix(inner_train_rows, selected + [candidate])`, score it
       on `_named_matrix(inner_validate_rows, selected + [candidate])`
       against `_labels(inner_validate_rows, spec)` — log loss for
       classification, MAE for regression (the same primary metrics
       `_metrics`/`_regression_metrics` already treat as primary; lower is
       better for both, so "improves" means "strictly lower").
     - Build a **shuffled** version of the same augmented matrix: same
       `selected` columns unchanged, but `candidate`'s column values
       permuted (`np.random.default_rng(seed_tuple).permutation(...)`,
       where `seed_tuple` is a deterministic function of `(seed,
       fold.test_season, len(selected), candidate)` — pick a concrete,
       documented construction, not something that changes between runs).
       Fit and score the same way on this shuffled variant.
     - `candidate` "passes" this step if the real-column score beats
       (is strictly lower than) the shuffled-column score — this is the
       actually-injected control comparison this project has used for
       every other threshold so far (stages 1-2's noise column,
       `MIN_PA`/`MIN_BIP`'s documented precedent-setting decisions); it is
       not a new kind of arbitrary epsilon.
     - Among candidates that pass this step, add the one with the largest
       margin (real score minus shuffled score, most-improved direction) to
       `selected`, remove it from `remaining`. Record every candidate's
       real/shuffled scores at this step, not just the winner's — the
       evidence trail matters as much as the outcome, matching stages 1-2's
       per-fold reporting granularity.
     - If no remaining candidate passes, stop (standard forward-stepwise
       termination). Also stop if `remaining` is empty.
  6. Record per fold: `selected` (final ordered list), the full step-by-step
     trace (candidate, real score, shuffled score, added-or-not, at each
     step), and whether the fold was skipped.
- After all folds: aggregate into a stability summary — for each candidate
  feature, how many of the *evaluated* (non-skipped) outer folds selected
  it. Do not compute a final keep/drop verdict; this is evidence, same
  posture as stages 1-2.

Work package 3 — Persistence, CLI, docs:

- Add `migrations/0055_feature_selection_stepwise.sql`: `meta.
  feature_selection_stepwise` table, same shape as `meta.feature_selection`
  (`migrations/0054_feature_selection.sql`) — `selection_id`, `snapshot_id`
  FK, `target` FK, `fold_plan_json`, `method_config_json` (record
  `min_survival_fraction`, `seed`, probe-model names), `status`, `error`,
  `result_json`, `artifact_uri`, `artifact_sha256`, timestamps. Same
  idempotent reuse-by-`selection_id` pattern as `select_features()`.
- Add `select-features-stepwise` under the `experiment` CLI subcommand,
  taking `--snapshot` (target is read from the snapshot, same reasoning as
  the prior two packages — no redundant `--target` flag).
- `docs/EXPERIMENT_RUNBOOK.md`: document the command, the 70%-survival
  candidate-set derivation, the inner-split mechanics, and — same as
  before — that this is diagnostic evidence, not a selection decision.
- `docs/DECISIONS.md`: new ADR recording the design, explicitly noting it
  implements ADR-065's own stage-3 recommendation and which specific
  mechanics (scoring metric, shuffled-control threshold, seeding
  construction) it filled in beyond what ADR-065 sketched.
- `docs/TABLE_CONTRACTS.md`, `plans/04-modeling-simulation-and-experiments.md`
  (04E status), `plans/PROGRESS.md`: update in the same change.
- **File size check:** `feature_select.py` was ~305 lines at `442f47e`.
  If adding this package pushes it much past ~550-600 lines, split the
  stepwise logic into a new sibling module (e.g.
  `mlb_baseball/model/feature_select_stepwise.py`) that imports shared
  helpers from `feature_select.py`, rather than letting one file keep
  growing indefinitely. Either way, state which you chose and why in the
  ADR — this is a judgment call, not a hard rule, but it shouldn't be a
  silent one.

Work package 4 — Tests:

- Unit (`tests/unit/`): a synthetic test proving the paired real-vs-shuffled
  comparison actually separates a genuinely informative feature from a pure
  noise one (same spirit as `test_feature_select_synthetic.py`'s existing
  tests, adapted for the stepwise real/shuffled mechanic instead of
  permutation importance). Test `_named_matrix()` directly against a small
  hand-built `SnapshotRow` fixture. Test that an empty candidate set (all
  features below the survival threshold) raises `ExperimentError` clearly.
- Integration (`tests/integration/`, against `mlb_test` only): using the
  existing `_seed()` fixture and `fold_years=(2016, 2017, 2018)` (see
  Repository Context — this fixture already supports both the skip case and
  the genuine nested case, don't add a new fixture unless you discover a
  real reason you must), prove: the `season-2016` fold is recorded as
  skipped with the stated reason; at least one of `season-2017`/
  `season-2018` produces a genuine stepwise trace; the whole run is
  idempotent (same `selection_id`, no duplicate row on rerun); the CLI
  command runs end to end.

Work package 5 — Close-out:

- Run the full test suite, Ruff, and mypy; fix anything until clean.
- Commit in coherent steps and push to `main` directly, per this repo's
  established direct-to-main workflow (`CLAUDE.md`).

Definition of done:
- `mlb experiment select-features-stepwise --snapshot <id>` works against
  both a real `home_win` and a real `run_differential` snapshot in
  `mlb_test`.
- The empty-inner-data case is handled gracefully (skip, not crash) and is
  covered by a real test against the existing fixture, not just defensive
  code that never runs.
- The real-vs-shuffled paired comparison is the sole "improves" threshold —
  no separate arbitrary epsilon was introduced.
- No change to `run()`, `compare()`, `_predictions()`, `_probabilities()`,
  or `select_features()`'s existing behavior.
- No production `mlb` read or write occurred. No new runtime dependency.
- Full pytest suite, Ruff, and mypy pass clean.
- Docs listed in Work Package 3 updated in the same change as the code.
- Commits pushed to `main`.
- End with: changed files, exact test results, the actual stepwise trace
  output from at least one real (non-skipped) fold in the test run (not
  just "tests passed" — show what got selected and why), and a specific
  recommendation for what should happen next now that all three feature-
  selection stages exist (e.g. running this against full production-scale
  history once such a snapshot exists, or moving on to a different part of
  the design spec).
