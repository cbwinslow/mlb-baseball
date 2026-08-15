# Goal seek: close PIT-04/PLN-01 admission bookkeeping, implement PIT-03 starter workload

Goal: `docs/FEATURE_ADMISSION_QUEUE.md`'s "Recommended next implementation
package" names `pitcher_workload_v1` as three admission-queue rows (PLN-01
probable starter state, PIT-03 starter rest/workload, PIT-04 bullpen
fatigue) as if none of them exist yet. Direct code inspection during this
session's scoping found that's wrong for two of the three: PIT-04 and PLN-01
are already implemented and shipped, just never formally closed in the
queue's own bookkeeping. Only PIT-03 is a genuine gap. This package (a)
closes PIT-04/PLN-01 with real evidence, the same way `team_prior_offense_defense_v1`'s
own admission-closure package did (issue #8/ADR-062 — read that precedent
before starting), and (b) implements PIT-03, the actual new work.

Safety and scope:
- Use `mlb_test` for every migration, fixture, and test. Production `mlb`
  may be queried **read-only**, and only for the same kind of era-coverage
  evidence issue #8's closure package gathered — never migrated, conformed,
  or written to.
- No new runtime dependency.
- PIT-03 covers the **Retrosheet-historical path only** (`compute()`,
  mirroring `starter.py`/`bullpen.py`'s own `compute()`). Do **not** build
  `compute_live()` (2026 live season via `raw.mlb_playbyplay`) or
  `compute_probable()`/`compute_upcoming()` (forward-looking scheduled
  games) in this package — every sibling family (`starter.py`, `bullpen.py`,
  `offense.py`) built its historical path first and added live/probable
  paths as separate, later, dated work; follow that exact precedent rather
  than trying to do all three at once. State this explicitly as a
  deliberate scope cut in your final report, and recommend the live/probable
  extension as the next follow-up package.
- Do not touch `starter.py`'s or `bullpen.py`'s existing quality/fatigue
  computations — this package only adds a new, separate column family and
  closes two admission-queue rows in documentation.
- Do not wire the new module into `run()`/`build_feature_stage()` or
  `game_base_v1` — every sibling enrichment family is currently reachable
  only via its own `compute()` and via `model.health_check()`, not the live
  pipeline (production `gold.game_feature` population remains blocked
  behind Plan 01F). Match that exact, current, dormant-until-wired status.

Repository context (read before writing code — this is a generalization on
top of very deliberately-designed existing patterns, not a from-scratch
design):

- `docs/FEATURE_ADMISSION_QUEUE.md` — read PIT-03, PIT-04, and PLN-01's full
  rows (lines ~40, ~43, ~50) and the "Evidence rules" section at the top.
  Also read OFF-01/02/03/08 and DEF-01's rows to see exactly what a closed,
  fully-evidenced row's annotation looks like — your PIT-04/PLN-01 closures
  should match that same style and rigor, not just assert "done."
- `mlb_baseball/model/bullpen.py` (whole file) and
  `mlb_baseball/sql/team_bullpen_retrosheet_update.sql` (whole file) — this
  is PIT-03's direct template. Specifically reuse:
  - The `starters` CTE pattern (`resp_pit_start_fl = 'T'`, `bat_home_id`
    convention for home/away pitcher attribution) — already proven correct
    and tested for identifying which pitcher started a given team's side of
    a given game.
  - The day-collapse-then-`RANGE`-frame pattern (`team_day_outs` →
    `team_day_fatigue` in that file) — this is the fix ADR-042 made after
    an earlier per-row lateral join took 20+ minutes against full
    production data (434K team-game rows). PIT-03's per-*pitcher* rolling
    window needs the exact same collapse-first shape, keyed by
    `pitcher_retro_id` instead of `team_id` this time — read ADR-042
    (`docs/DECISIONS.md`) for the full reasoning before reproducing this
    pattern, don't just copy the SQL shape without understanding why it's
    shaped that way.
  - The parameterized single-window choice: bullpen fatigue deliberately
    implemented one trailing window (`fatigue_days`, not both a 7-day and a
    30-day variant) with the reasoning "narrowed to what's cheaply and
    unambiguously derivable ... this project doesn't have yet" (see the
    module docstring). PIT-03's admission-queue row lists both a 7-day and
    a 14-day window as options — follow bullpen's precedent and implement
    **one** parameterized window (`workload_days`, mirroring
    `fatigue_days`'s exact naming shape), not both, unless you find a
    concrete reason mid-implementation that changes this — note the choice
    and why in the ADR either way.
  - Units: outs, not pitches — `raw.retrosheet_event` has `event_outs_ct`
    per play but no pitch-level count in this project's ingested source
    (pitch-by-pitch counts are a different, separate Retrosheet product
    this project doesn't ingest). Using outs here matches bullpen_fatigue's
    own precedent and is honest about what's actually derivable, not a
    downgrade — state this explicitly in the new module's docstring the
    same way bullpen.py's docstring is explicit about its own scope limits.
- `mlb_baseball/model/starter.py` (whole file) — the column-naming
  convention to match (`home_starter_k_pct`/`away_starter_k_pct`, etc.,
  from `migrations/0016_starter_rate_stats.sql`) and the `health_check()`
  reconciliation-against-`raw.bref_pitching` pattern, though PIT-03 has
  nothing in `raw.bref_pitching` to reconcile against (rest days and
  workload outs aren't published season aggregates) — its health check
  needs a different, still-real verification; see Work Package 3.
- `docs/DECISIONS.md` — read ADR-042 (bullpen fatigue's day-collapse
  performance fix) and ADR-061/062 (`team_prior_offense_defense_v1`'s
  original implementation and its later admission-closure package) as the
  two most directly relevant precedents for this package's two halves.
- Migrations currently end at `0055_feature_selection_stepwise.sql` — the
  new migration for this package is `0056`.

Work package 1 — Close PIT-04 (bullpen fatigue) in the admission queue:

- Verify `home_bullpen_fatigue`/`away_bullpen_fatigue` (`migrations/
  0020_bullpen.sql`, computed by `team_bullpen_retrosheet_update.sql`)
  actually satisfies PIT-04's declared requirements: "NULL/coverage flag
  for unresolved roles" and "timeline and doubleheader fixture." Check
  `tests/integration/test_model_bullpen.py` for whether a doubleheader
  fixture test already exists for the fatigue column specifically (not just
  for quality) — if one doesn't, that's a real gap to close in this
  package, following the exact model of how `team_prior_offense_defense_v1`'s
  own closure package added the doubleheader/suspended-game test it was
  missing (`ee92003`, cited in OFF-08's row).
- Update PIT-04's row in `docs/FEATURE_ADMISSION_QUEUE.md` to the same
  "now / medium — implemented, `bullpen.py` (ADR-039/042)..." style every
  other closed row already uses, citing the actual commit(s)/tests that
  prove it, not just asserting it.

Work package 2 — Close PLN-01 (probable starter state) in the admission
queue:

- Verify `raw.mlb_probable` + `starter.py::compute_probable()` +
  `team_starter_probable_update.sql` actually satisfy PLN-01's declared
  requirements: "explicit unknown/change flag" and "capture timestamp and
  later-change regression [test]." Read `mlb_baseball/connectors/mlb_api.py`'s
  `_probable_rows`/`_new_probable_rows`/`_latest_probables`/`_load_probable`
  functions (around line 2819-2890) to confirm `raw.mlb_probable` is
  genuinely append-only with a capture timestamp, and check whether an
  existing test proves a *later-announced change* (a probable pitcher
  announcement that gets revised) is captured correctly, not just the
  first announcement. If that regression test doesn't exist, that's a real
  gap — either close it in this package if it's small, or explicitly leave
  it open in the admission-queue row with a stated reason (matching
  DEF-01's precedent of explicitly noting one declared sub-item stayed
  open rather than silently dropping it).
- Update PLN-01's row in `docs/FEATURE_ADMISSION_QUEUE.md` the same way.

Work package 3 — Implement PIT-03 (starter rest/workload), Retrosheet-
historical path only:

- New migration `migrations/0056_starter_workload.sql`: add
  `home_starter_rest_days`/`away_starter_rest_days` (nullable integer —
  NULL for a pitcher's first tracked start, no prior start to measure
  from) and `home_starter_outs_{N}d`/`away_starter_outs_{N}d` (nullable
  numeric, where `{N}` is whatever `workload_days` value you land on per
  the Repository Context guidance above — e.g. `home_starter_outs_7d` if
  you pick 7) to `gold.game_feature`.
- New module `mlb_baseball/model/starter_workload.py`, following
  `bullpen.py`'s exact structure: a module docstring stating scope and
  citing the reused patterns (day-collapse, outs-not-pitches, single
  window) and their sources (ADR-042, bullpen.py's own docstring); a
  `compute(conn) -> int` gated on `raw.retrosheet_event`'s existence
  exactly like every sibling `compute()`; a `health_check() -> list[Check]`.
- New SQL resource `mlb_baseball/sql/starter_workload_retrosheet_update.sql`,
  following `team_bullpen_retrosheet_update.sql`'s exact shape: identify
  each game's starter per team-side (reuse the `starters` CTE pattern
  directly, don't reinvent it), then for `home_starter_rest_days`: for that
  specific starting pitcher (by `resp_pit_id`), find their immediately
  preceding start's `game_date` (a per-pitcher, not per-team, rolling
  lookup — `LAG()` over `PARTITION BY pitcher_retro_id ORDER BY game_date,
  game_id` restricted to rows where `resp_pit_start_fl = 'T'` for that
  pitcher) and compute the day difference; for `home_starter_outs_{N}d`:
  the day-collapse-then-`RANGE`-frame pattern from `team_bullpen_retrosheet_update.sql`,
  keyed by `pitcher_retro_id`, summing **all** of that pitcher's outs
  (any role, not just starts) in the trailing window before today's game.
- Hand-computed fixture tests in `tests/integration/test_model_starter_workload.py`
  (new file): pick a real, identifiable pitcher-and-date combination the
  same way `starter.py`'s own docstring did (a real, verifiable case, not a
  synthetic one, if practical — otherwise a carefully hand-built fixture
  with the exact same rigor as `team_rate.py`'s tests), proving rest-days
  and workload-outs match a hand calculation exactly, and proving a
  pitcher's very first tracked start correctly leaves both columns NULL
  rather than 0 or an error.
- `health_check()`: rest-days/workload-outs have no external published
  source to reconcile against the way `starter.py`'s ERA/K%/BB% do against
  `raw.bref_pitching` — instead, write a coverage-style check (e.g. what
  fraction of resolved-starter rows have a non-NULL rest-days value beyond
  a season's first few weeks, using the shared helpers in
  `mlb_baseball/health.py` — check what's available there before writing a
  new one).

Work package 4 — Close-out:

- `docs/TABLE_CONTRACTS.md`: add the two new column pairs to the
  `gold.game_feature` contract row.
- `docs/DECISIONS.md`: new ADR covering both halves of this package — the
  PIT-04/PLN-01 closure evidence, and PIT-03's design (single-window
  choice, outs-not-pitches, Retrosheet-only scope cut).
- `plans/03-research-statistics-and-features.md` and `plans/PROGRESS.md`:
  dated entries.
- Run the full test suite, Ruff, and mypy; fix anything until clean.
- Commit in coherent steps (the admission-queue closures and the new PIT-03
  implementation are different enough to be separate commits, your
  judgment on exact grouping) and push to `main` directly, per this repo's
  established direct-to-main workflow (`CLAUDE.md`).

Definition of done:
- PIT-04 and PLN-01 are either fully closed in `docs/FEATURE_ADMISSION_QUEUE.md`
  with real, cited evidence, or explicitly left open with a stated reason
  for whichever specific sub-requirement isn't met — never silently
  asserted done without evidence.
- PIT-03's Retrosheet-historical path is implemented, tested with
  hand-computed fixtures, and its two deliberate scope cuts (single window,
  Retrosheet-only) are stated plainly, not glossed over.
- No production `mlb` write occurred; any production read was scoped to
  evidence-gathering only.
- No change to `starter.py`'s or `bullpen.py`'s existing computations.
- Full pytest suite, Ruff, and mypy pass clean.
- Docs updated in the same change as the code.
- Commits pushed to `main`.
- End with: changed files, exact test results, the specific evidence used
  to close (or not close) PIT-04/PLN-01, and a recommendation for the
  live/probable-path follow-up package this one deliberately deferred.
