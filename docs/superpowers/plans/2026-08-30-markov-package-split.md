# markov/ Package Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the single 1,150-line `mlb_baseball/model/markov.py` into a `markov/` package with a pure-computation `core` module (no I/O) and a DB-reading `estimate` module, with **zero behaviour change**.

**Architecture:** `markov/core.py` holds every function and dataclass that operates on in-memory values (state model, transition-matrix normalization, run-expectancy linear solve, outcome distributions, empirical-Bayes shrink, half-inning/game/in-game simulators, arsenal edge math). `markov/estimate.py` holds the ~10 functions that take a `psycopg.Connection` and read Retrosheet/Statcast, plus the packaged SQL constants. `markov/__init__.py` re-exports the full public surface so every existing `import markov` / `markov.X` call keeps working unchanged.

**Tech Stack:** Python 3.11, `psycopg` 3, `numpy`, `pytest`, `ruff`, `mypy`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-30-matchup-model-design.md` (this is its "step 0"). Motivation: ADR-275 names the split as a follow-up; the matchup model needs `core` importable without a DB.

## Global Constraints

- **Naming:** package dir `markov/`, modules `core.py` / `estimate.py` — one or two words, per `CLAUDE.md` "Naming convention".
- **No behaviour change.** The entire existing test suite must pass unchanged after every task. No test is rewritten except its import line.
- **`uv run` only** — `uv run pytest …`, `uv run ruff …`, `uv run mypy`. Never bare `pytest`/`pip`.
- **Definition of done** (`CLAUDE.md`): tests pass, `uv run ruff check .` + `uv run ruff format --check .` + `uv run mypy` clean, commit each finished task.
- **Commit trailer** on every commit:
  ```
  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01FKxUUvFgMbChP1vt9ybDKv
  ```
- Work on a branch off `main` (`refactor/markov-package`), PR into `main`. No direct push to `main`.

---

## File Structure

| Path | Responsibility | Change |
|---|---|---|
| `mlb_baseball/model/markov/__init__.py` | Public surface: `from .core import *` + `from .estimate import *`, plus an explicit `__all__`. Nothing else. | Create |
| `mlb_baseball/model/markov/core.py` | All pure computation — no `psycopg`, no `read_sql`, no `conn`. | Create (moved from `markov.py`) |
| `mlb_baseball/model/markov/estimate.py` | Every `conn: psycopg.Connection` function + the `_*_SQL = read_sql(...)` constants. Imports what it needs from `.core`. | Create (moved from `markov.py`) |
| `mlb_baseball/model/markov.py` | Deleted — replaced by the package. | Delete |
| `tests/unit/test_markov_*.py` (6 files) | Unchanged except: `from mlb_baseball.model.markov import X` still resolves via `__init__`; `from mlb_baseball.model.markov.core import Y` allowed where a test wants to prove core has no DB. | Modify (imports only, if at all) |
| `tests/integration/test_model_markov.py`, `test_model_sim_predict.py` | Same — imports only. | Modify (if at all) |
| `mlb_baseball/model/sim_predict.py`, `run_expectancy.py`, `scripts/verify_markov_calibration.py` | Consumers. `import markov` / `markov.X` must keep working — verified, not changed, unless a direct `from mlb_baseball.model.markov import _private` breaks. | Verify |

### What goes where (exhaustive — the split is mechanical)

**`core.py`** — dataclasses `BaseOutState`, `MarkovError`, `DegenerateSimulation`, `TransitionCountRow`, `Outcome`, `GameResult`, `PitchArsenal`, `BatterArsenalProfile`, `InGameSimulationResult`; constants `MATCHUP_PRIOR_PA`, `TERMINAL`, `EMPTY_ZERO_OUTS`, `TRANSIENT_STATES`, `_UNRESOLVED_TRIAL_LIMIT`, `SIM_MAX_INNINGS`; functions `_pre_state`, `_post_state`, `_validate_row_conservation`, `_validate_probabilities_sum_to_one`, `_validate_seasons`, `_validate_bat_home`, `build_transition_matrix`, `_immediate_expected_runs`, `run_expectancy`, `build_outcome_distribution`, `shrink_outcome_distribution`, `simulate_half_inning_steps`, `simulate_half_inning`, `simulate_half_innings`, `simulate_game`, `simulate_home_win_rate`, `summarize_runs`, `compute_arsenal_matchup_edge`, `adjust_outcome_distribution_for_matchup`, `simulate_matchup_game`, `_simulate_remainder_of_game`, `simulate_in_game_win_probability`.

**`estimate.py`** — SQL constants `_TRANSITION_COUNTS_SQL`, `_MATCHUP_COUNTS_SQL`, `_HALF_INNING_RUNS_SQL`, `_GAME_SCORES_SQL`, `_PITCHER_ARSENAL_SQL`, `_BATTER_ARSENAL_SQL`; functions `_retrosheet_tables_ready`, `_fetch_transition_counts`, `estimate_transition_matrix`, `estimate_run_expectancy`, `estimate_outcome_distribution`, `fetch_matchup_transition_counts`, `estimate_matchup_distribution`, `real_half_inning_runs`, `real_game_scores`, `fetch_pitcher_arsenal`, `fetch_batter_arsenal`.

`estimate.py` imports from `.core`: `BaseOutState`, `MarkovError`, `Outcome`, `TransitionCountRow`, `GameResult`, `PitchArsenal`, `BatterArsenalProfile`, `MATCHUP_PRIOR_PA`, `build_transition_matrix`, `_immediate_expected_runs`, `run_expectancy`, `build_outcome_distribution`, `shrink_outcome_distribution`, `_validate_seasons`, `_validate_bat_home` (confirm exact set against the moved code — the estimator functions call these).

---

## Task 1: Capture the current public surface as a baseline

**Files:**
- Create: `tests/unit/test_markov_public_surface.py`

**Interfaces:**
- Consumes: nothing.
- Produces: a regression test other tasks run to prove `import markov` still exposes the same names.

- [ ] **Step 1: Write the surface-lock test**

```python
"""markov's public import surface must not change across the package split."""

from mlb_baseball.model import markov

# Every name production code and tests import from `markov` today. If the
# package split drops or renames one, this fails before anything else does.
_EXPECTED = {
    # dataclasses / errors
    "BaseOutState", "MarkovError", "DegenerateSimulation", "TransitionCountRow",
    "Outcome", "GameResult", "PitchArsenal", "BatterArsenalProfile",
    "InGameSimulationResult",
    # constants
    "MATCHUP_PRIOR_PA", "TERMINAL", "EMPTY_ZERO_OUTS", "TRANSIENT_STATES",
    "SIM_MAX_INNINGS",
    # pure computation
    "build_transition_matrix", "run_expectancy", "build_outcome_distribution",
    "shrink_outcome_distribution", "simulate_half_inning_steps",
    "simulate_half_inning", "simulate_half_innings", "simulate_game",
    "simulate_home_win_rate", "summarize_runs", "compute_arsenal_matchup_edge",
    "adjust_outcome_distribution_for_matchup", "simulate_matchup_game",
    "simulate_in_game_win_probability",
    # DB estimators
    "estimate_transition_matrix", "estimate_run_expectancy",
    "estimate_outcome_distribution", "fetch_matchup_transition_counts",
    "estimate_matchup_distribution", "real_half_inning_runs",
    "real_game_scores", "fetch_pitcher_arsenal", "fetch_batter_arsenal",
}


def test_markov_exposes_every_expected_name():
    missing = {n for n in _EXPECTED if not hasattr(markov, n)}
    assert not missing, f"markov no longer exports: {sorted(missing)}"
```

- [ ] **Step 2: Run it against the current single-file module — must PASS**

Run: `uv run pytest tests/unit/test_markov_public_surface.py -v`
Expected: PASS (the single-file `markov.py` already exports all of these).

If any name is missing here, STOP — the list is wrong, fix it against `mlb_baseball/model/markov.py` before proceeding.

- [ ] **Step 3: Commit**

```bash
git checkout -b refactor/markov-package
git add tests/unit/test_markov_public_surface.py
git commit -m "test: lock markov's public import surface before the package split

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FKxUUvFgMbChP1vt9ybDKv"
```

---

## Task 2: Create the package skeleton with everything still in one place

Move the whole body of `markov.py` into `markov/core.py` first, with a
re-exporting `__init__.py`. `estimate.py` is created empty-but-importable.
This proves the package *mechanism* works before splitting responsibilities.

**Files:**
- Create: `mlb_baseball/model/markov/__init__.py`
- Create: `mlb_baseball/model/markov/core.py`
- Create: `mlb_baseball/model/markov/estimate.py`
- Delete: `mlb_baseball/model/markov.py`

**Interfaces:**
- Consumes: the surface test from Task 1.
- Produces: `mlb_baseball.model.markov` importable as a package; `markov.core` importable.

- [ ] **Step 1: Make the package directory and move the file**

```bash
mkdir mlb_baseball/model/markov
git mv mlb_baseball/model/markov.py mlb_baseball/model/markov/core.py
```

- [ ] **Step 2: Write `__init__.py`**

```python
"""Base/out Markov chain: `core` is pure computation, `estimate` reads the DB.

This package was one 1,150-line module (`markov.py`). The split (ADR-275
follow-up) lets `core` be imported and unit-tested with no database, which
the plate-appearance matchup model needs. The public surface is unchanged --
every name that used to be `markov.X` is re-exported here.
"""

from mlb_baseball.model.markov.core import *  # noqa: F401,F403
from mlb_baseball.model.markov.core import __all__ as _core_all
from mlb_baseball.model.markov.estimate import *  # noqa: F401,F403
from mlb_baseball.model.markov.estimate import __all__ as _estimate_all

__all__ = [*_core_all, *_estimate_all]
```

- [ ] **Step 3: Add `__all__` to `core.py`**

At the top of `core.py`, after the imports, add an explicit `__all__` listing
every public name (the `_EXPECTED` set from Task 1 minus the estimator names,
plus `EMPTY_ZERO_OUTS`, `_simulate_remainder_of_game` stays private/omitted).
Private helpers (`_pre_state`, `_validate_*`, `_immediate_expected_runs`,
`_UNRESOLVED_TRIAL_LIMIT`) are NOT in `__all__` but stay importable by
`estimate.py` via `from .core import _name`.

```python
__all__ = [
    "BaseOutState", "MarkovError", "DegenerateSimulation", "TransitionCountRow",
    "Outcome", "GameResult", "PitchArsenal", "BatterArsenalProfile",
    "InGameSimulationResult", "MATCHUP_PRIOR_PA", "TERMINAL", "EMPTY_ZERO_OUTS",
    "TRANSIENT_STATES", "SIM_MAX_INNINGS",
    "build_transition_matrix", "run_expectancy", "build_outcome_distribution",
    "shrink_outcome_distribution", "simulate_half_inning_steps",
    "simulate_half_inning", "simulate_half_innings", "simulate_game",
    "simulate_home_win_rate", "summarize_runs", "compute_arsenal_matchup_edge",
    "adjust_outcome_distribution_for_matchup", "simulate_matchup_game",
    "simulate_in_game_win_probability",
]
```

- [ ] **Step 4: Create `estimate.py` as a stub that re-exports nothing yet**

```python
"""DB-reading estimators for the base/out Markov chain (moved from markov.py
in Task 3). Everything here takes a psycopg.Connection and reads Retrosheet
or Statcast, then hands in-memory values to markov.core.
"""

__all__: list[str] = []
```

- [ ] **Step 5: Run the surface test + the full markov suite**

Run:
```
uv run pytest tests/unit/test_markov_public_surface.py tests/unit/test_markov_game.py tests/unit/test_markov_simulate.py tests/unit/test_markov_shrink.py tests/unit/test_markov_transitions.py tests/unit/test_markov_arsenal.py -v
```
Expected: ALL PASS. (`core.py` still holds everything; `__init__` re-exports it.)

- [ ] **Step 6: Run the integration + consumer tests**

Run:
```
TEST_DATABASE_URL=postgresql:///mlb_test uv run pytest tests/integration/test_model_markov.py tests/integration/test_model_sim_predict.py tests/integration/test_model_run_expectancy.py -q
```
Expected: ALL PASS.

- [ ] **Step 7: ruff + mypy**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy`
Expected: clean. (Fix `__init__.py` star-import noise with the `# noqa` shown; `__all__` makes `mypy --strict`'s re-export check pass.)

- [ ] **Step 8: Commit**

```bash
git add mlb_baseball/model/markov/ && git rm mlb_baseball/model/markov.py 2>/dev/null; true
git commit -m "refactor: markov.py -> markov/ package (all code still in core.py)

Mechanical: single module becomes a package, __init__ re-exports core's
public surface. estimate.py is an empty stub; Task 3 moves the DB functions.
No behaviour change -- full markov suite + integration + consumers green.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FKxUUvFgMbChP1vt9ybDKv"
```

---

## Task 3: Move the DB estimators from `core.py` to `estimate.py`

**Files:**
- Modify: `mlb_baseball/model/markov/core.py` (remove the 11 estimator functions + 6 SQL constants + the `psycopg` / `read_sql` / `fetch_one` imports if now unused)
- Modify: `mlb_baseball/model/markov/estimate.py` (receive them)

**Interfaces:**
- Consumes: `markov.core` pure functions/types.
- Produces: `markov.estimate.estimate_matchup_distribution(conn, ...)` etc., re-exported through `markov/__init__.py` unchanged.

- [ ] **Step 1: Move the SQL constants**

Cut these six lines from `core.py`, paste into `estimate.py` after its
docstring:
```python
from mlb_baseball.sql import read_sql

_TRANSITION_COUNTS_SQL = read_sql("markov_transition_counts.sql")
_MATCHUP_COUNTS_SQL = read_sql("markov_transition_counts_matchup.sql")
_HALF_INNING_RUNS_SQL = read_sql("markov_half_inning_runs.sql")
_GAME_SCORES_SQL = read_sql("markov_game_scores.sql")
_PITCHER_ARSENAL_SQL = read_sql("pitcher_arsenal_select.sql")
_BATTER_ARSENAL_SQL = read_sql("batter_arsenal_select.sql")
```

- [ ] **Step 2: Move the 11 estimator functions**

Cut from `core.py`, paste into `estimate.py` (keep their relative order):
`_retrosheet_tables_ready`, `_fetch_transition_counts`, `estimate_transition_matrix`,
`estimate_run_expectancy`, `estimate_outcome_distribution`,
`fetch_matchup_transition_counts`, `estimate_matchup_distribution`,
`real_half_inning_runs`, `real_game_scores`, `fetch_pitcher_arsenal`,
`fetch_batter_arsenal`.

- [ ] **Step 3: Add `estimate.py`'s imports**

At the top of `estimate.py`:
```python
from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Literal

import psycopg

from mlb_baseball.db import fetch_one
from mlb_baseball.model.markov.core import (
    MATCHUP_PRIOR_PA,
    BaseOutState,
    BatterArsenalProfile,
    GameResult,
    MarkovError,
    Outcome,
    PitchArsenal,
    TransitionCountRow,
    _immediate_expected_runs,
    _validate_bat_home,
    _validate_seasons,
    build_outcome_distribution,
    build_transition_matrix,
    run_expectancy,
    shrink_outcome_distribution,
)
```
Then set `__all__` to the 9 public estimator names (the `_`-prefixed two
stay out of `__all__` but are still importable):
```python
__all__ = [
    "estimate_transition_matrix", "estimate_run_expectancy",
    "estimate_outcome_distribution", "fetch_matchup_transition_counts",
    "estimate_matchup_distribution", "real_half_inning_runs",
    "real_game_scores", "fetch_pitcher_arsenal", "fetch_batter_arsenal",
]
```

- [ ] **Step 4: Prune now-unused imports from `core.py`**

Run `uv run ruff check mlb_baseball/model/markov/core.py` — it will flag
`psycopg`, `fetch_one`, `Literal`, `date` as unused if nothing pure needs
them. Remove exactly what ruff flags. (Keep `numpy` — `run_expectancy`
uses it. Keep `Literal` only if a pure signature still uses it — check.)

- [ ] **Step 5: Run the full markov + integration + consumer suite**

Run:
```
uv run pytest tests/unit/ -q -k markov
TEST_DATABASE_URL=postgresql:///mlb_test uv run pytest tests/integration/test_model_markov.py tests/integration/test_model_sim_predict.py tests/integration/test_model_run_expectancy.py tests/integration/test_eval_markov_holdout.py -q
```
Expected: ALL PASS, same counts as before the split.

- [ ] **Step 6: Prove `core` has no DB dependency**

Add to `tests/unit/test_markov_public_surface.py`:
```python
def test_core_imports_without_a_database_driver(monkeypatch):
    # core must not pull psycopg or the SQL loader at import time.
    import sys

    for mod in [m for m in sys.modules if m.startswith("mlb_baseball.model.markov")]:
        monkeypatch.delitem(sys.modules, mod, raising=False)
    monkeypatch.setitem(sys.modules, "psycopg", None)  # importing psycopg now raises
    import mlb_baseball.model.markov.core  # must not raise
```

Run: `uv run pytest tests/unit/test_markov_public_surface.py -v` — PASS.

- [ ] **Step 7: ruff + format + mypy**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add mlb_baseball/model/markov/
git commit -m "refactor: move markov DB estimators to markov/estimate.py

core.py is now pure -- no psycopg, no read_sql -- and imports with the DB
driver absent (new test). estimate.py holds the 11 conn-taking functions +
the SQL constants. Public surface unchanged (surface test green).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FKxUUvFgMbChP1vt9ybDKv"
```

---

## Task 4: Point internal consumers at the specific module (optional tidy)

Not required for correctness — `markov.X` still works everywhere. Do this
only if a consumer reads a **private** name that shouldn't cross the package
boundary.

**Files:**
- Verify: `mlb_baseball/model/sim_predict.py`, `mlb_baseball/model/run_expectancy.py`, `scripts/verify_markov_calibration.py`

- [ ] **Step 1: Grep for private cross-module imports**

Run:
```
rg "from mlb_baseball.model.markov import .*_" mlb_baseball/ scripts/ tests/
rg "markov\._" mlb_baseball/ scripts/
```
Expected: no matches. If there ARE matches, the consumer is reaching into a
private helper — either make it public in `core`/`estimate` (add to
`__all__`) or refactor the consumer. Document which in the commit.

- [ ] **Step 2: If clean, no change. Commit only if Step 1 required edits.**

---

## Task 5: Update the docs and open the PR

**Files:**
- Modify: `docs/ARCHITECTURE.md` (if it names `model/markov.py` — grep first)
- Modify: `docs/DECISIONS.md` — close ADR-275's "the matchup work is a good forcing function to do that split" by noting it's done, or add a one-line ADR-276 if the reviewer prefers.
- Modify: `plans/PROGRESS.md` — append the standard progress entry.

- [ ] **Step 1: Grep for stale path references**

Run: `rg "model/markov\.py|model\.markov\.py" docs/ plans/ README.md`
Fix each hit to `model/markov/` or `model.markov` (the package).

- [ ] **Step 2: PROGRESS.md entry**

Append (match the file's existing entry format — date header, what changed, verification):
```markdown
## 2026-08-30 — markov/ package split (spec step 0)

Split `mlb_baseball/model/markov.py` (1,150 lines) into `markov/core.py`
(pure: state model, RE solve, simulators, shrink) and `markov/estimate.py`
(11 conn-taking functions + SQL constants). `__init__.py` re-exports the
full surface — no caller changed. New `test_markov_public_surface.py` locks
the surface and proves `core` imports with `psycopg` absent.

Verification: full markov unit suite + `test_model_markov`,
`test_model_sim_predict`, `test_model_run_expectancy`,
`test_eval_markov_holdout` on `mlb_test` green (same counts); ruff, format,
mypy clean.
```

- [ ] **Step 3: Full suite once more, then push + PR**

Run:
```
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest tests/unit -q
TEST_DATABASE_URL=postgresql:///mlb_test uv run pytest tests/integration -q -k "markov or sim_predict or run_expectancy or eval_markov"
```

```bash
git add docs/ plans/PROGRESS.md
git commit -m "docs: record the markov/ package split (PROGRESS, path refs)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FKxUUvFgMbChP1vt9ybDKv"
git push -u origin refactor/markov-package
gh pr create --title "refactor: markov.py -> markov/ package (core vs estimate)" \
  --body "Spec step 0 of docs/superpowers/specs/2026-08-30-matchup-model-design.md. Zero behaviour change: __init__ re-exports the full surface, every existing markov.X call works. core.py is now pure (imports with psycopg absent — new test). Prereq for the matchup model's clean library signatures."
```

---

## Self-Review

**Spec coverage:** This plan implements only spec step 0 (the package split). Steps 1–8 of the spec get their own plans. ✅

**Placeholder scan:** Task 4 is conditional ("only if Step 1 finds matches") — that's a real branch, not a placeholder; both outcomes are specified. Task 5 Step 1 says "fix each hit" for an unknown set of doc references — acceptable because the fix is mechanical (one path string) and the exact hits can't be known until grep runs. No "TBD"/"add error handling"/"write tests for the above". ✅

**Type consistency:** `estimate.py`'s import list in Task 3 Step 3 must match the names the moved functions actually call — Task 3 Step 4 (ruff) and Step 5 (tests) catch any mismatch. The `__all__` lists in Task 2 Step 3 and Task 3 Step 3 partition the Task 1 `_EXPECTED` set (core gets the non-estimator names, estimate gets the 9 estimator names) — cross-checked. `_simulate_remainder_of_game` and `InGameSimulationResult`: `InGameSimulationResult` is in core's `__all__`; `_simulate_remainder_of_game` is private, stays in core, not exported — consistent with it not being in Task 1's `_EXPECTED`. ✅

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-30-markov-package-split.md`. Two execution options:

1. **Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session with checkpoints for review.

Which approach?
