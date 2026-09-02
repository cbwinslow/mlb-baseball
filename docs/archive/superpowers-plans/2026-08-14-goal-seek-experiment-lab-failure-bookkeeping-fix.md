# Goal seek: fix lost failure-bookkeeping in the experiment lab, and close the last doctor-coverage gap

Goal: Fix a confirmed, real bug found by an independent code review of commit
range `442f47e..3676ac2` (the feature-selection stage 1-2 and stage 3
packages), which on inspection turned out to also affect the original
target-agnostic framework package. It is not new to any one package — it is
the same copy-pasted run-lifecycle pattern in three places. This package
fixes the root cause once, closes a related graceful-degradation gap the
same review flagged, and closes the one genuine `mlb doctor` coverage gap
that's left (most of what looked like a gap in earlier session notes turns
out to already be wired in — see Work Package 3 for the corrected picture).

Primary outcome: a failed `mlb experiment run` / `mlb experiment
select-features` / `mlb experiment select-features-stepwise` invocation
leaves a real, queryable `status = 'failed'` row in its `meta.*` table —
verified by a regression test that reproduces the exact real-world failure
path (through a connection used as its own context manager, the same way
`cli.py`'s `with get_connection() as conn:` uses it), not the workaround the
existing test happens to use today.

Safety and scope:
- Use `mlb_test` for every fixture, test, and database write. Production
  `mlb` is not touched — not even read-only.
- No new runtime dependency, no migration needed — this is pure Python
  logic; no schema changes.
- Do not touch the actual feature-selection or regression algorithms
  (`_probabilities`, `_predictions`, `_metrics`, `_regression_metrics`, the
  stage-1/2 permutation/embedded logic, the stage-3 stepwise search itself).
  This package only touches how a *failure* is recorded, plus one small,
  directly-related graceful-skip addition and one doctor-wiring line.
- Do not refactor the success-path run-lifecycle boilerplate (check-existing
  → insert 'running' → compute → update 'success') into the same shared
  helper unless you find a genuinely clean way to do it without adding
  indirection that makes the three modules' already-reviewed success paths
  harder to read. The confirmed bug is specifically in the failure path;
  don't let this turn into a larger rewrite than the bug calls for.

Repository context (read before writing code — this fix touches code from
all three prior packages; re-verify the facts below against the real files,
they were confirmed once already but line numbers may have moved):

- **The confirmed bug, exact mechanism:** `mlb_baseball/model/experiment.py`
  `run()`'s except block (currently around line 1027-1063) does
  `conn.rollback()`, then `INSERT INTO meta.experiment (...) VALUES (...,
  'failed', ...) ON CONFLICT (...) DO UPDATE SET status = 'failed', ...`,
  then `raise` — with **no `conn.commit()` before the raise**. `cli.py`
  calls `run()`/`select_features()`/`select_features_stepwise()` inside
  `with get_connection() as conn:` (`mlb_baseball/db.py::get_connection()`
  is a bare `psycopg.connect(...)` — the `with` block relies entirely on
  psycopg3's own `Connection.__exit__`, which commits on clean exit and
  **rolls back on a propagating exception**). So when the except block's own
  `raise` propagates out through that `with` block, psycopg3's own rollback
  fires a second time and wipes out the 'failed' row the except block just
  wrote. The process still exits non-zero (the crash is visible in the
  terminal), but the database — the thing `meta.experiment`'s `status IN
  ('running', 'success', 'failed')` contract exists to make queryable —
  ends up with **zero record** that the run was ever attempted.
- **Why the existing test doesn't catch this — read it yourself, don't take
  this on faith:** `tests/integration/test_experiment.py::
  test_failed_experiment_is_recorded_without_corrupting_success` (around
  line 262-287) calls `experiment.run(db_conn, bad)` bare inside `pytest.raises(...)`,
  then calls `db_conn.commit()` **itself**, immediately after, before
  asserting the failed row exists. That manual commit is what makes the
  test pass — it's testing a different code path than what `cli.py` actually
  runs. Confirm this by reading the test directly.
- **The same pattern, same bug, in two more places:**
  `mlb_baseball/model/feature_select.py::select_features()`'s except block
  (currently around line 278-300) and `mlb_baseball/model/
  feature_select_stepwise.py::select_features_stepwise()`'s except block
  (currently around line 381-403) — same `conn.rollback()` → INSERT-or-UPDATE
  'failed' → `raise` shape, same missing commit, same real-world loss when
  invoked through the CLI.
- **The `mlb doctor` coverage picture — corrected from an earlier, partially
  wrong assessment made mid-session:** `mlb_baseball/doctor.py` (around line
  222-226) already calls `experiment.health_check()` **directly**, separate
  from `model.health_check()`'s aggregate (`mlb_baseball/model/__init__.py`,
  which covers `features`/`log5`/`gbm`/`starter`/`park`/`offense`/
  `team_rate`/`war`/`bullpen`/`oaa`/`speed`/`framing`/`market` — not
  `experiment`). This means `meta.experiment_target`, `meta.
  experiment_snapshot`, `gold.game_feature_snapshot`, and **`meta.
  feature_selection`** (added to `experiment.py`'s own `health_check()` list
  by the stage-1/2 package) are **already** covered by `mlb doctor` — do not
  "fix" this, it isn't broken. The one genuine, currently-unwired gap:
  `mlb_baseball/model/feature_select_stepwise.py::health_check()` (checks
  `meta.feature_selection_stepwise`) is never called from `doctor.py` or
  from `model.health_check()`'s aggregate — confirm this yourself with a
  direct read of `doctor.py`, don't assume. Separately,
  `mlb_baseball/model/feature_select.py::health_check()` duplicates the
  exact same `meta.feature_selection` check `experiment.py` already covers
  — it's harmless dead code (redundant, not a gap), not required reading to
  fix in this package; leave it alone unless removing it is genuinely
  trivial and you note the decision in the ADR.
- **The related, currently-unaddressed crash risk:** in
  `feature_select_stepwise.py`, the existing empty-row guard (checks
  `inner_train_rows`/`inner_validate_rows` are non-empty, records a graceful
  `"insufficient inner-split data"` skip if not) does not check that
  `inner_train_rows` contains both classes for a `classification` target.
  Confirmed live and reachable against real data during this session (not
  hypothetical): a real 386-game, 2015-2024 rehearsal sample in `mlb_test`
  ran both `home_win` and `run_differential` through `select-features-stepwise`
  successfully without triggering it, but the risk is real for smaller or
  more skewed inner-training windows — an inner-train slice that happens to
  be all-one-outcome will crash `LogisticRegression.fit` with an unhandled
  `ValueError`, aborting the entire stepwise run instead of gracefully
  skipping just that fold.

Work package 1 — Shared failure-bookkeeping helper, and the actual fix:

- Add one function to `mlb_baseball/model/experiment.py` (alongside the
  other private helpers like `_write_artifact`): `_finalize_failed_run(conn:
  psycopg.Connection, sql: str, params: tuple[Any, ...]) -> None`. Its job:
  `conn.rollback()` (undo whatever the failed computation partially wrote),
  execute the caller-supplied failure INSERT/UPDATE SQL, then **`conn.commit()`**
  — the actual fix. Docstring should state plainly why the commit is there:
  so this survives even when the caller uses this connection as its own
  context manager and would otherwise roll back a second time on the
  propagating exception.
- Replace `run()`'s except-block body (rollback + INSERT + raise) with a
  call to `_finalize_failed_run(conn, <the same INSERT SQL currently
  there>, <the same params>)` followed by `raise`. Keep the SQL text itself
  local to `run()` — only the rollback/commit sequencing is shared, per the
  Safety and scope note above about not over-refactoring.

Work package 2 — Same fix in `feature_select.py`:

- Import `_finalize_failed_run` from `mlb_baseball.model.experiment` (same
  pattern `feature_select.py` already uses for its other imports from that
  module). Replace `select_features()`'s except-block body the same way,
  keeping its own INSERT SQL local.

Work package 3 — Same fix in `feature_select_stepwise.py`, plus the
graceful single-class skip:

- Same `_finalize_failed_run` fix in `select_features_stepwise()`'s except
  block (import from `experiment.py`, same as `feature_select.py` already
  does).
- Extend the existing inner-split emptiness check: after confirming
  `inner_train_rows`/`inner_validate_rows` are non-empty, for a
  `classification`-task target also confirm `inner_train_rows` contains
  both `home_win` outcomes (`len(set(_labels(inner_train_rows,
  spec).tolist())) >= 2`, or equivalent — check what `_labels` actually
  returns before writing this, it's a numpy array). If not, record that
  fold as skipped with reason `"single-class inner-training split"` (a
  distinct reason string from `"insufficient inner-split data"` — a future
  reader should be able to tell the two failure modes apart from the
  persisted result alone) and continue to the next fold, exactly matching
  the existing empty-data skip's shape. This check is not needed for
  `regression` targets (MAE doesn't require class balance).

Work package 4 — Close the one real doctor-coverage gap:

- In `mlb_baseball/doctor.py`, add a direct call to
  `feature_select_stepwise.health_check()`, mirroring the existing
  `experiment.health_check()` block exactly (same try/except-appends-a-
  failing-Check shape, same style comment if one fits). Import
  `feature_select_stepwise` the same way `experiment` is already imported
  there. Do not touch the `experiment.health_check()` or
  `model.health_check()` wiring — both are already correct, per Repository
  Context above.

Work package 5 — Tests (this is the core deliverable — a fix without a test
that would have caught the original bug isn't done):

- For each of the three modules, add (or extend an existing test near the
  current `test_failed_experiment_is_recorded_without_corrupting_success`-
  style test) a regression test that reproduces the **real** failure path:
  wrap the call in `with db_conn:` (the test's real psycopg3 connection
  fixture used as its own context manager — this exercises the exact same
  `__enter__`/`__exit__` semantics `get_connection()`'s object has in
  `cli.py`, since `get_connection()` is just `psycopg.connect(...)`),
  **not** a bare call followed by a manual `db_conn.commit()`. Something
  like:
  ```python
  with pytest.raises(SomeExpectedError):
      with db_conn:
          experiment.run(db_conn, bad_config)
  # deliberately no db_conn.commit() here — if the bug were still present,
  # the failed row would not exist at this point.
  assert db_conn.execute(
      "SELECT status FROM meta.experiment WHERE experiment_id = %s",
      (experiment_id,),
  ).fetchone() == ("failed",)
  ```
  Verify for yourself that using `db_conn` as its own context manager here
  doesn't leave it unusable for the test's own cleanup/reset calls
  afterward (check psycopg3's actual `Connection.__exit__` behavior — it
  commits/rolls back, it does not close the connection — but confirm this
  against the installed version rather than trusting this prompt). Write
  the equivalent test for `feature_select.select_features()` and
  `feature_select_stepwise.select_features_stepwise()`.
- A test proving the new single-class graceful skip: construct (or reuse/
  extend the existing rehearsal fixture with) a scenario where an inner-
  training window is deliberately single-outcome, and assert the fold is
  recorded as skipped with reason `"single-class inner-training split"`
  rather than the whole call raising.
- A test (or extend `tests/unit/test_doctor.py` if one exists — check
  first) proving `feature_select_stepwise.health_check()` is now actually
  reachable from `doctor.py`'s aggregated checks.

Work package 6 — Docs and close-out:

- `docs/DECISIONS.md`: new ADR recording the bug (exact mechanism, which
  three call sites had it, why the existing test didn't catch it), the fix
  (the shared `_finalize_failed_run` helper and why only the failure path
  was factored, not the success path), the single-class graceful-skip
  addition, and the doctor-coverage correction (most of what looked like a
  gap was already covered; only `feature_select_stepwise` genuinely wasn't).
- `plans/PROGRESS.md`: dated entry.
- Run the full test suite, Ruff, and mypy; fix anything until clean.
- Commit in coherent steps and push to `main` directly, per this repo's
  established direct-to-main workflow (`CLAUDE.md`).

Definition of done:
- A failed `run()`/`select_features()`/`select_features_stepwise()` call,
  invoked the way `cli.py` actually invokes it (connection used as its own
  context manager), leaves a real `status = 'failed'` row in its table —
  proven by a test that would have failed before this fix and passes after.
- The single-class inner-training case is a graceful per-fold skip, not a
  crash, and is covered by a real test.
- `feature_select_stepwise.health_check()` is reachable from `mlb doctor`.
- No change to any actual modeling/selection algorithm.
- No production `mlb` read or write occurred. No new dependency, no
  migration.
- Full pytest suite, Ruff, and mypy pass clean.
- Docs updated in the same change as the code.
- Commits pushed to `main`.
- End with: changed files, exact test results including the specific
  before/after behavior of the new regression test (show that it would have
  caught the original bug — e.g. by describing what it asserts and why that
  assertion is the one the old code path would have failed), and confirmation
  that `mlb doctor` now reports on all three experiment-lab tables.
