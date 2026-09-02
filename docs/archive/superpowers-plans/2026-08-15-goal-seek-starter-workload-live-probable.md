# Goal seek: starter workload live/probable paths (pitcher_workload_v1_live)

Goal: Extend `mlb_baseball/model/starter_workload.py` (PIT-03, landed
`edce0b5`/`b5c022f`, closed today) with the two paths its own closure
explicitly deferred: `compute_live()` (completed 2026 games, via
`raw.mlb_playbyplay`) and `compute_probable()` (upcoming scheduled games,
via `raw.mlb_probable`), bringing it to parity with `starter.py`'s own
three-path shape — the module this one was already modeled on for its
historical path.

Primary outcome: `home_starter_rest_days`/`away_starter_rest_days` and
`home_starter_outs_7d`/`away_starter_outs_7d` are populated for completed
2026 games (gap `compute()` can't reach — it depends on
`raw.retrosheet_event`, which covers 1910-2025 only) and for upcoming
scheduled games with an announced probable pitcher, using the exact same
leakage-safe "strictly before this game's own date" discipline
`starter.py::compute_probable()` already proved out.

Safety and scope:
- Use `mlb_test` for every migration, fixture, and test. Production `mlb`
  is not touched — not even read-only (this package needs no evidence-
  gathering step, unlike the admission-closure package before it).
- No new runtime dependency, no new migration (the four columns this
  package fills already exist from `migrations/0056_starter_workload.sql`).
- Do not touch `starter.py`'s or `bullpen.py`'s own `compute_live()`/
  `compute_probable()`/`compute_upcoming()` — read them for the pattern,
  don't modify them.
- Do not touch `starter_workload.py`'s existing `compute()` (the
  Retrosheet-historical path) or its migration/columns.
- Do not wire the new functions into `run()`/`build_feature_stage()` —
  same dormant-until-wired posture as every sibling live/probable path
  (Plan 01F still blocks production cutover).

Repository context (read before writing code — this package is a close
structural mirror of two already-shipped, already-tested functions, not a
new design):

- `mlb_baseball/model/starter.py`'s `compute_live()` and `compute_probable()`
  (read both in full) plus their SQL,
  `mlb_baseball/sql/team_starter_live_update.sql` and
  `mlb_baseball/sql/team_starter_probable_update.sql` (read both in full —
  this package's two new SQL files are close structural cousins of these,
  not a from-scratch design). Specifically reuse:
  - **`compute_live()`'s starter identification:** the `first_pitcher` CTE
    (`SELECT DISTINCT ON (game_pk, half_inning) game_pk, half_inning,
    pitcher_id FROM raw.mlb_playbyplay ORDER BY game_pk, half_inning,
    at_bat_index::int` — the pitcher on the very first play of each side's
    half-inning is that side's starter). Reuse this exact shape.
  - **`compute_live()`'s outs-diff:** `raw.mlb_playbyplay`'s `outs` column
    is a *running* per-half-inning count (0/1/2, resets each half-inning),
    not "outs on this specific play" — `play_outs`'s `LAG(outs::int, 1, 0)
    OVER (PARTITION BY game_pk, inning, half_inning ORDER BY
    at_bat_index::int)` diff is how every sibling module already handles
    this; reuse it verbatim, don't rederive it.
  - **`compute_live()`'s gate:** `WHERE f.home_starter_era IS NULL` — this
    package's live path gates the same way, but on **this module's own**
    columns: `WHERE f.home_starter_rest_days IS NULL` (or equivalent — the
    point is only filling what `compute()` left NULL for 2026, not
    re-deriving rows `compute()` already resolved from Retrosheet).
  - **`compute_probable()`'s probable-pitcher resolution:**
    `latest_probable`'s `SELECT DISTINCT ON (game_pk, side) ... ORDER BY
    _loaded_at DESC` — always takes the *most recently captured* snapshot,
    so a later scratch/rotation-swap correctly overrides an earlier
    announcement. Reuse verbatim.
  - **`compute_probable()`'s leakage guard — the single most important
    piece of this whole package:** its `home_quality`/`away_quality` CTEs
    join a target's own pitcher history with `s.game_date < t.game_date`
    (the *target game's own date*, not "as of today" / not `now()`) —
    because a probable can be announced several days before the actual
    game, and that pitcher might make another start in the gap. This
    package's trailing-workload and rest-days calculations need the exact
    same discipline: a pitcher's rest-days/workload entering a probable
    game must only ever look at that pitcher's own appearances strictly
    before **that specific target game's** date, not today's date. Get this
    wrong and the feature leaks future information relative to its own
    declared cutoff — this is exactly the class of bug
    `docs/GAME_INSTANCE_IDENTITY.md`/ADR-032 exist to prevent. Read
    `test_compute_probable_only_uses_history_strictly_before_target_game_date`
    in `tests/integration/test_model_starter.py` (already exists, already
    passing) to see exactly what this guard's own regression test proves —
    your new tests need an equivalent for rest-days/workload specifically.
  - **`compute_probable()`'s upcoming-game targeting:** `targets`' `WHERE
    f.home_win IS NULL AND (hp.pitcher_id IS NOT NULL OR ap.pitcher_id IS
    NOT NULL)` and its dating via `raw.mlb_schedule` (not `core.game`,
    which never holds an unplayed game) — reuse this shape.
- `mlb_baseball/model/starter_workload.py` (whole file, as it exists after
  today's `edce0b5`) — the exact column names
  (`home_starter_rest_days`/`away_starter_rest_days`/
  `home_starter_outs_7d`/`away_starter_outs_7d`), the `WORKLOAD_WINDOW_DAYS
  = 7` constant, and the day-collapse `RANGE`-frame pattern its own
  `compute()` already uses — the live/probable paths need the *same*
  trailing-window logic, just re-derived from `raw.mlb_playbyplay`/
  `raw.mlb_schedule` dates instead of Retrosheet dates.
- `docs/DECISIONS.md` ADR-068 — this package's own predecessor; read its
  "Revisit if" clause (it names exactly this follow-up).
- `docs/FEATURE_ADMISSION_QUEUE.md`'s PIT-03 row — update its closure text
  once this package lands (it currently says "Live/probable paths
  deliberately deferred to follow-up package").

Work package 1 — `compute_live()`:

- New SQL resource `mlb_baseball/sql/starter_workload_live_update.sql`:
  reuse `team_starter_live_update.sql`'s `first_pitcher`/`play_outs` CTEs
  to identify each 2026 completed game's starters and their per-play outs,
  then apply this module's own day-collapse `RANGE`-frame trailing-window
  sum (parameterized `workload_days`, matching `compute()`'s own parameter
  name) and per-pitcher `LAG(game_date)`-over-starts-only rest-days logic —
  both keyed by `pitcher_id` (the `raw.mlb_playbyplay` identity space) this
  time, not `pitcher_retro_id`. Gate the final `UPDATE` on this module's
  own NULL columns, mirroring `compute_live()`'s exact gating shape.
- `starter_workload.py::compute_live(conn) -> int`: same
  `to_regclass('raw.mlb_playbyplay')` existence gate as every sibling
  `compute_live()`, calls the new SQL resource, returns `cur.rowcount`.

Work package 2 — `compute_probable()`:

- New SQL resource `mlb_baseball/sql/starter_workload_probable_update.sql`:
  reuse `team_starter_probable_update.sql`'s `latest_probable`/`targets`
  CTEs to find upcoming games with an announced probable, then compute
  each probable pitcher's rest-days (most recent prior start strictly
  before **that target game's own date**) and trailing-workload outs (same
  window, same strict-date-before-target discipline) from their own
  `raw.mlb_playbyplay` history. This needs its own starter-identification
  within that history too (reuse the `first_pitcher`-per-`game_pk`-per-
  `half_inning` shape to know which of the probable pitcher's *own* past
  appearances were themselves starts, for the rest-days calculation
  specifically — the workload-outs sum counts any role, same as
  `compute()`'s own historical logic).
- `starter_workload.py::compute_probable(conn) -> int`: same dual
  `to_regclass('raw.mlb_probable')`/`to_regclass('raw.mlb_playbyplay')`
  existence gate as `starter.py::compute_probable()`.

Work package 3 — Tests:

- `tests/integration/test_model_starter_workload.py` (extend the existing
  file): add live-path tests mirroring
  `test_compute_live_rolling_fip_and_rates_match_hand_calculation`/
  `test_compute_live_does_not_overwrite_retrosheet_derived_values` from
  `test_model_starter.py` (same fixture-building style, adapted to this
  module's rest-days/workload-outs values instead of FIP/rates) — a hand-
  computed 2026 scenario, and a proof that `compute_live()` never
  overwrites a row `compute()` already resolved.
  Add probable-path tests mirroring
  `test_compute_probable_populates_upcoming_game_from_latest_announced_probable`
  and, critically,
  `test_compute_probable_only_uses_history_strictly_before_target_game_date`
  — this second one is the leakage-safety proof and is not optional. Also
  mirror `test_compute_probable_returns_zero_without_probable_or_playbyplay_table`.
  Hand-compute every expected value the same rigor as the historical
  path's own tests from today — show the arithmetic in comments, the same
  way `test_compute_starter_workload_matches_hand_calculation` already
  does.

Work package 4 — Close-out:

- `mlb_baseball/model/__init__.py`: no change needed (already imports
  `starter_workload` and its `health_check()` from today's package) unless
  `health_check()` itself needs a live/probable-specific check — read what
  `starter.py::health_check()` does for its own probable-coverage check
  (`test_health_check_flags_missing_probable_coverage`) and decide whether
  an equivalent belongs here; note the decision either way.
- `docs/FEATURE_ADMISSION_QUEUE.md`: update PIT-03's row — it currently
  says live/probable paths are deferred; update that sentence now that
  they're not.
- `docs/DECISIONS.md`: extend ADR-068 or add a new ADR (your judgment,
  note which and why) documenting the two new paths and confirming they
  reuse `starter.py`'s proven patterns rather than reinventing them.
- `plans/PROGRESS.md`: dated entry.
- Run the full test suite, Ruff, and mypy; fix anything until clean.
- Commit in coherent steps and push to `main` directly, per this repo's
  established direct-to-main workflow (`CLAUDE.md`).

Definition of done:
- `compute_live()` and `compute_probable()` exist, are tested, and never
  overwrite a row `compute()` already resolved.
- The leakage-safety guard (strictly-before-target-game's-own-date) is
  implemented and has a real regression test proving it, not just asserted
  in prose.
- No change to `starter.py`, `bullpen.py`, or `starter_workload.py`'s
  existing `compute()`.
- No production `mlb` access of any kind.
- Full pytest suite, Ruff, and mypy pass clean.
- Docs updated in the same change as the code, including closing out
  PIT-03's "deferred" language in the admission queue.
- Commits pushed to `main`.
- End with: changed files, exact test results (re-run the full suite
  yourself and report the real number, not an approximation — today's
  prior package self-reported an inaccurate pass count that didn't match
  independent re-verification, so get this right), and confirmation the
  leakage-safety test actually exercises the announced-days-ahead-of-
  another-start scenario, not just a same-day case.
