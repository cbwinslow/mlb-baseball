# Goal seek: close issue #8 (team_prior_offense_defense_v1 completion)

Goal: Complete the outstanding admission-queue contract for
`team_prior_offense_defense_v1` — GitHub issue #8
(github.com/cbwinslow/mlb-baseball/issues/8).

Primary outcome:
`team_rate.py`'s rate-stat columns (OBP/SLG/ISO/BB%/K%, admission queue
OFF-01/02/03) and run-environment columns (OFF-08) landed their core
formulas in an earlier package, but each row's own declared sub-requirements
did not fully land: no min-sample gate, no retained PA/denominator, no
suspended/doubleheader test for the run-environment side, and no measured
era-coverage evidence for OFF-01. Bring the family up to its full declared
contract. This is a completion package for already-shipped, already-tested
code — not new feature scope, not a new admission-queue row.

Safety and scope:
- Use `mlb_test` for all migrations, fixtures, tests, and database writes.
- Production `mlb` may be queried read-only only, and only for the
  era-coverage measurement (work package 4). Never migrate, rebuild,
  truncate, conform, write predictions, or alter any production object.
- Preserve every existing migration, column, and test. Do not rename or
  drop `home_obp`/`home_slg`/etc. or any of the 14 columns from migration
  `0050`. Additive changes only (new columns via a new migration if needed).
- Do not touch `team_woba_retrosheet_update.sql` (that gap is tracked
  separately in issue #9) or any admission-queue row besides OFF-01/02/03/08
  and DEF-01.
- Do not add MLflow, Optuna, LightGBM, PyTorch, or any new runtime
  dependency.
- Do not implement, or expand into, any other admission-queue row (OFF-04+,
  PIT-*, PLN-*, CTX-*, STA-*, etc.) — those remain out of scope regardless
  of how tempting they look while in this file.
- Do not wire `team_rate.py` into `run()`/`build_feature_stage()` or into
  `game_base_v1` — that remains a separate, later, explicitly-gated decision
  per `docs/FEATURE_REGISTRY.md`.

Repository context:
- Issue #8 (full text has the row-by-row gap table) and issue #9 (the
  separately-tracked paper-cuts list, not this package's job) are both live
  on `cbwinslow/mlb-baseball`.
- `mlb_baseball/model/team_rate.py`, `mlb_baseball/sql/
  team_rate_retrosheet_update.sql`, `mlb_baseball/sql/
  team_run_environment_update.sql`, `tests/integration/
  test_model_team_rate.py`, `migrations/0050_team_prior_offense_defense.sql`,
  `docs/DECISIONS.md` (ADR-061), `docs/FEATURE_ADMISSION_QUEUE.md` are all
  already in place from the prior two packages (commits through `db97d96`).
- The most recent fix (`db97d96`) added a `bat_event_fl='T'` guard and
  game-number-based doubleheader ordering to the rate-stat SQL, and already
  added a doubleheader-ordering test — issue #8's doubleheader-test item for
  OFF-02 is therefore already closed; do not redo it.
- `mlb field-census --exact` is the existing, repeatable-read, read-only
  raw-metadata/coverage inventory tool (`mlb_baseball/field_census.py`) —
  use it for work package 4 rather than writing new ad-hoc queries.

Work package 1 — Min-sample gate for the rate-stat columns:
- Research this codebase's own precedent for small-sample handling before
  picking a threshold: read `offense.py`'s wOBA docstring and
  `health_check()` (it documents small-sample noise but does NOT gate it —
  note explicitly whether you're establishing new precedent or following
  an existing one, and say so in the ADR/docs update). Check whether any
  other module (starter.py, bullpen.py, oaa.py, speed.py, framing.py) has
  an actual `NULL below N` gate and, if so, what N and why.
- Choose and document a defensible minimum-PA (or minimum-AB, whichever is
  the more natural denominator per stat) threshold below which OBP/SLG/
  ISO/BB%/K% become NULL instead of a small-sample noisy value. Cite the
  reasoning (e.g. a commonly-used sabermetric minimum-PA qualification
  threshold scaled to an early-season entering-value context, not a
  season-total qualification threshold — those are different things; do
  not blindly copy a "batting title qualifier" number without checking it
  fits this use case).
- Implement the gate in `team_rate_retrosheet_update.sql`'s `computed` CTE.
  Add a hand-computed fixture test proving a below-threshold row is NULL
  and an at/above-threshold row is not.

Work package 2 — Retained PA/denominator column:
- Add `home_pa`/`away_pa` (or a name consistent with this codebase's
  one-or-two-word convention) via a new migration (next number after
  `0050`) on `gold.game_feature`, nullable numeric or integer.
- Populate it in the same `team_rate_retrosheet_update.sql` UPDATE (the PA
  value is already computed as an intermediate in the `computed`/`rate`
  CTEs — expose it, don't recompute it a second time).
- This directly satisfies OFF-03's "retain PA and missing flag" — the
  min-sample gate from work package 1 doubles as the missing/low-confidence
  flag (NULL rate columns + a populated but below-threshold PA column tells
  a consumer exactly why a row is NULL).
- Extend the hand-computed fixture test to assert the PA value.

Work package 3 — Suspended/doubleheader test for run-environment:
- `compute_run_environment()` (OFF-08/DEF-01) has a doubleheader-ordering
  test gap and no suspended-game test. Note that `compute_run_environment()`
  derives its values purely from `gold.game_feature`'s own already-computed
  `home_wins`/`home_losses`/`home_runs_for`/`home_runs_allowed` — so this
  test is really validating that the *base* family
  (`game_feature_rebuild.sql`, migration 0046) correctly excludes a
  postponed/suspended game from `wins`/`losses`/`runs_for` accumulation, and
  that `compute_run_environment()`'s division correctly reflects that. Read
  `docs/GAME_INSTANCE_IDENTITY.md` and the existing suspended/postponed
  handling in `game_feature_rebuild.sql` before writing this fixture — do
  not guess at how suspended games are represented in `core.game`.
- Add one fixture test: a postponed/suspended game plus a doubleheader
  (make-up game same or different date), confirming
  `home_runs_for_avg`/`home_runs_allowed_avg` only count actually-completed
  games in the correct order, matching OFF-08's stated requirement.

Work package 4 — Era-coverage evidence for OFF-01:
- Run `mlb field-census --exact` (read-only) to measure actual historical
  coverage of `raw.retrosheet_event`'s relevant fields (event_cd, ab_fl,
  sf_fl, bat_event_fl) across eras — OFF-01's row explicitly calls for
  "measure historical eras," which was never done.
- Record the actual measured coverage (not an assumption) in
  `docs/RAW_CORE_GOLD_FIELD_CENSUS.md` or `docs/FEATURE_ADMISSION_QUEUE.md`
  as appropriate, following the existing evidence-recording convention in
  those docs (verified database evidence, clearly separated from proposed
  future work, per that doc's own "Evidence rules" section).

Work package 5 — Close-out:
- Update the 5 admission-queue rows (OFF-01/02/03/08, DEF-01) in
  `docs/FEATURE_ADMISSION_QUEUE.md` to reflect the now-complete contract
  (remove the "core formula implemented... outstanding" wording from the
  last package once each row's own declared requirements are actually met —
  if any sub-item is deliberately still not done, say so explicitly and
  why, don't silently drop it from the row).
- Add an ADR-062 (or next available number) documenting the min-sample
  threshold decision and its rationale, following the existing ADR format.
- Update `plans/03-research-statistics-and-features.md`'s 03G section and
  `plans/PROGRESS.md` with a dated entry.
- Run the full test suite, Ruff, and mypy; fix anything until clean.
- Commit (one coherent change per work package, or one combined change —
  your judgment, following this project's "small coherent steps" commit
  culture) and push to `main` directly, matching this repository's
  established direct-to-main workflow (see `CLAUDE.md`).
- Close issue #8 with a comment summarizing exactly what landed, citing
  commit SHAs, once the full suite is green and the docs are updated. If
  any work package is deliberately deferred (e.g. era-coverage measurement
  turns out to need a longer production read-only session than is safe to
  run unattended), leave that item open in the issue rather than closing it
  falsely, and explain why in a comment.

Definition of done:
- Every row's previously-declared-but-missing requirement (min-sample gate,
  retained PA, suspended/doubleheader test, era-coverage evidence) is either
  delivered with tests, or explicitly left open in issue #8 with a stated
  reason — never silently dropped.
- No production writes occurred; all writes are `mlb_test` only.
- Full pytest suite, Ruff, and mypy pass clean.
- Docs (`docs/FEATURE_ADMISSION_QUEUE.md`, `docs/DECISIONS.md`,
  `plans/03-research-statistics-and-features.md`, `plans/PROGRESS.md`) are
  updated in the same change as the code, not as a follow-up.
- Commits are pushed to `main`.
- End with: changed files, exact test results, which issue #8 items closed
  vs. deliberately left open (and why), and a specific recommendation for
  what comes after issue #8 (likely: start on issue #9, or move on to a
  genuinely new admission-queue package).
