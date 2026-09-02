# Goal seek: code-quality pass on the ML experiment lab

Goal: A focused code-quality/DevOps-standards pass over the ML modeling
harness (`mlb_baseball/model/experiment.py`, `feature_select.py`,
`feature_select_stepwise.py`, and the `experiment` command dispatch in
`mlb_baseball/cli.py`) — the code landed across the four packages this
session (`05919ec`, `442f47e`, `3676ac2`, `0d69fe7`). This is a polish pass,
not a bug hunt (that's already been done twice, independently, on this same
code) and not a redesign. Every item below is a concrete finding from a
direct read of the current code, not a generic "clean this up" instruction —
treat the list as the actual scope, not a starting point to expand from.

**Read this first, it changes how you should approach the whole package:**
most of this codebase already matches CLAUDE.md's stated standards —
consistent naming, type hints throughout (mypy passes clean), no bare
excepts, no silent failures, no reinvented wheels (sklearn/XGBoost used
directly, no custom ML primitives). Most private helper functions in
`experiment.py` (e.g. `_canonical_json`, `_matrix`, `_labels`,
`_probabilities`, `_aggregate_metrics`) have **no docstring**, and that is
the codebase's own existing, consistent convention for short, self-
explanatory private helpers — not a gap introduced by this session's work,
and not something to "fix" by adding blanket docstrings everywhere. Adding
docstrings to functions that don't have one anywhere else in this style
would be inventing a new house rule, not enforcing an existing one. Match
what's already there; don't pad it.

**Update before you start:** while scoping this package, an automated review
surfaced a real, currently-broken command hiding in exactly this area:
`experiment_run`'s `--seed` argparse argument had been accidentally deleted
in `442f47e` (a copy/move mistake while adding `--seed` to the new
`select-features` subparser), crashing every real `mlb experiment run`
invocation with `AttributeError`. That's already fixed and committed
(`70e92fa`, with a new regression test,
`test_experiment_run_command_parses_all_its_own_arguments` in
`tests/unit/test_cli_dispatch.py`) — do not re-fix it, but do read that test
before starting Work Package 5 below, since it's the pattern the missing
tests for the other three subcommands should follow. The root cause of why
it went unnoticed for three packages is directly relevant to this package's
scope: `tests/unit/test_cli_dispatch.py` had (until that one fix) zero CLI-
dispatch-level coverage for `experiment run`/`compare`/`select-features`/
`select-features-stepwise` — every other test exercised the underlying
Python functions directly, never through `cli.main([...])` and real
argparse. Work package 5 closes the rest of that gap.

Safety and scope:
- Use `mlb_test` for every test run. Production `mlb` is not touched.
- No new runtime dependency, no migration, no schema change.
- Do not touch any actual modeling/selection/scoring logic — no changes to
  `_probabilities`, `_predictions`, `_metrics`, `_regression_metrics`, the
  stage-1/2/3 algorithms, or any estimator/parameter handling. This is
  strictly documentation, dead-code removal, and dispatch-code structure.
- Do not refactor the run-lifecycle boilerplate (check-existing → insert
  'running' → compute → update 'success') that's still duplicated across
  the three modules beyond the failure path. That was a **deliberate,
  documented decision** (ADR-067's rationale: "keeping SQL queries and
  success-path execution local to each module to avoid introducing
  unnecessary indirection across already-reviewed success paths"). Don't
  relitigate it in this package. If you find a genuinely new, concrete
  problem it causes that ADR-067 didn't anticipate, note it in the ADR for
  this package instead of unilaterally reversing that decision.
- Do not touch any `cli.py` command besides `experiment` (`migrate`,
  `ingest`, `backup`, `restore`, `evaluate`, etc. are all out of scope —
  `cli.py`'s `main()` is a large function well beyond just the ML harness;
  fixing that wholesale is not this package's job).

Work package 1 — Remove genuinely dead code:

- `mlb_baseball/model/feature_select.py::health_check()` (currently around
  line 302-305) checks `meta.feature_selection` — but
  `mlb_baseball/model/experiment.py::health_check()` **already** checks the
  same table (added by the stage-1/2 package), and `mlb doctor`
  (`doctor.py`) never calls `feature_select.health_check()` — confirmed
  directly: `grep -rn "feature_select.health_check"` across the codebase
  returns nothing. This function is unreachable, redundant dead code.
  Delete it, and delete the now-unused `Check`/`check_table_exists` imports
  in that file if nothing else in the module still needs them (check before
  removing — verify with a real grep, don't assume).

Work package 2 — Fix the stale module docstring:

- `mlb_baseball/model/experiment.py`'s module docstring (lines 1-6) still
  says: *"Reproducible, point-in-time game-win experiments. This is
  intentionally a small lab, not a generic AutoML framework. It makes one
  approved feature family, calendar folds, probability models, and the full
  evidence trail reusable."* That described the pre-`05919ec` single-target
  version. The module now supports two targets (`home_win` classification,
  `run_differential` regression) via `TargetSpec`/`TARGET_REGISTRY`, and its
  sibling modules `feature_select.py`/`feature_select_stepwise.py` build
  directly on it. Rewrite the docstring to describe the current reality —
  target-agnostic experiment lab, calendar folds, transparent baselines
  through full estimator families, the feature-selection stability
  reporting it now anchors — in the same terse, technical style the rest of
  this codebase's module docstrings use (look at
  `feature_select_stepwise.py`'s module docstring for the right length/tone
  to match). Keep the "not a generic AutoML framework" framing if it's
  still true — decide based on what the module actually does today, don't
  just delete the line reflexively.

Work package 3 — Extract the `experiment` CLI dispatch out of `main()`:

- `mlb_baseball/cli.py`'s `main()` function currently has the `experiment`
  command's dispatch (the `elif args.command == "experiment":` block,
  covering `snapshot`/`run`/`select-features`/`select-features-stepwise`)
  inline, nested three levels deep, spanning roughly 90 lines (currently
  around line 495-566). This has grown every package this session and will
  keep growing if a fourth feature-selection stage or a third target is
  ever added. Extract it into a dedicated function, e.g. `_run_experiment_command(args:
  argparse.Namespace, conn: psycopg.Connection) -> None`, defined near the
  other command handlers (match wherever this codebase already puts
  command-specific logic that's been extracted out of `main()` — check for
  precedent before picking a location, don't just guess). `main()`'s
  `experiment` branch becomes a short call to it inside the existing `with
  get_connection() as conn:` block. This is scoped strictly to the
  `experiment` command — do not touch how any other `cli.py` command is
  structured.

Work package 4 — De-duplicate the classification-vs-regression metric
formatting:

- The same branching shape — `if "log_loss" in <dict>: print(...) elif "mae"
  in <dict>: print(...)` — appears twice: once in the `run` sub-command's
  fold-result printer (currently around line 513-521), once in the `compare`
  fallback branch (currently around line 566-575). Factor this into one
  small helper, e.g. `_format_metrics_line(metrics: dict[str, Any]) ->
  str`, used by both. Keep the two call sites' actual prefix text as-is
  (`"  {fold}: ..."` vs. `"{model} {fold}: ..."`) — only the metric-value
  formatting itself needs to be shared, not the whole print statement;
  don't force an awkward common signature onto two genuinely different
  prefixes just to save a few more lines.

Work package 5 — Tests and close-out:

- Add CLI-dispatch-level tests for `experiment compare`,
  `experiment select-features`, and `experiment select-features-stepwise` —
  the same `MagicMock` connection + monkeypatched-function pattern
  `test_experiment_run_command_parses_all_its_own_arguments` and
  `test_experiment_snapshot_command_creates_and_prints_snapshot` already use
  in `tests/unit/test_cli_dispatch.py`, proving each subcommand's argparse
  arguments actually reach the function call (this is exactly the class of
  bug the `--seed` regression was — a test that only calls the underlying
  Python function directly would not have caught it; a test that goes
  through `cli.main([...])` would have).
- Add or update tests proving: `feature_select.health_check` no longer
  exists (or, if you decide against full removal for a reason you document,
  that it's at least reachable — but removal is the expected outcome here);
  the extracted `_run_experiment_command` produces identical CLI output to
  before for all four sub-commands (build these on top of the dispatch tests
  from the previous bullet, now that they exist for all four); the shared
  metrics-formatting helper produces the exact same strings the old inline
  code did for both a classification and a regression result.
- `docs/DECISIONS.md`: a short ADR is optional here — this is a pure
  refactor with no behavior change, so only add one if something genuinely
  decision-worthy came up (e.g. where you placed the extracted function and
  why). Don't manufacture a decision to write about if there isn't one.
- `plans/PROGRESS.md`: dated entry noting this was a quality/structure pass,
  no behavior change.
- Run the full test suite, Ruff, and mypy; fix anything until clean.
- Commit in coherent steps and push to `main` directly, per this repo's
  established direct-to-main workflow (`CLAUDE.md`).

Definition of done:
- `feature_select.py`'s dead `health_check()` is gone (or its continued
  existence is explicitly justified in the ADR).
- `experiment.py`'s module docstring accurately describes the current
  module.
- The `experiment` CLI dispatch is a named function, not inline in `main()`,
  and every one of its four sub-commands produces byte-identical output to
  before — prove this, don't just assert it.
- The metrics-formatting duplication between `run` and `compare` is gone.
- No modeling/selection logic changed. No behavior change anywhere —
  this package is observationally a no-op except for the two genuine fixes
  (dead code removed, docstring corrected).
- Full pytest suite, Ruff, and mypy pass clean.
- No production `mlb` access. No new dependency, no migration.
- Commits pushed to `main`.
- End with: changed files, exact test results, and explicit confirmation
  that CLI output for all four `experiment` sub-commands is unchanged
  (show a before/after comparison for at least one sub-command, not just a
  claim).
