# SQLMesh migration spike

Time-boxed spike evaluating SQLMesh as a replacement for `conform.py`'s
SQL-in-Python transformations. **Not part of the shipped pipeline** — this
directory is proof-of-concept output for a go/no-go decision (see the draft
ADR in `docs/DECISIONS.md`, marked DRAFT). Nothing here runs as part of
`mlb conform`, `mlb doctor`, or CI.

## Database safety

This project's SQLMesh gateway (`config.yaml`) points ONLY at `mlb_spike`, a
disposable local Postgres database — **never** `mlb` or `mlb_test*`. All
reads against real production `mlb` during this spike were plain `SELECT`
(via `psql`/`\copy`), never through SQLMesh itself.

## What's seeded into `mlb_spike`, and exactly how

`mlb_spike` holds a deliberately narrow slice of production `mlb`, just
enough to run and tie out the three ported models — not a full clone.

| Table | Scope copied | Row count | Why |
|---|---|---|---|
| `core.team` | full | 152 | small; team resolution needed by every model |
| `core.venue` | **not seeded** — see below | — | this is exactly what one of the 3 ported models rebuilds |
| `core.game` | full, all seasons | 227,016 | small (227K rows); park factor needs 3-season trailing windows, cheapest to just copy all of it |
| `raw.retrosheet_gameinfo` | full | 224,877 | small; needed for the `gametype = 'regular'` join `offense.py` does redundantly-but-faithfully |
| `raw.retrosheet_park` | full | 260 | small; source for the venue dimension |
| `raw.mlb_venue` | full | 1,667 | small; enrichment source for the venue dimension |
| `raw.retrosheet_event` | **seasons 2021–2024 only** | 766,690 (of 16,465,273 in prod) | full table is 10GB/115 seasons of history; team wOBA is a *within-season* rolling calc with no cross-season dependency, so 4 seasons is enough to tie out 2023's league average and 2024's team-level range, plus demonstrate an incremental add-a-season backfill |

This is historical spike evidence, not a reproduction recipe. Reuse the
already-existing `mlb_spike` only for the read-only/default SQLMesh checks, and
reuse `mlb_test_codex` with the isolated candidate namespace for future
integration verification. Do not create, seed from production, or drop a
database as part of this workflow.

**`core.venue` was deliberately NOT seeded as a table** — one of the three
ported models rebuilds it from `raw.retrosheet_park`/`raw.mlb_venue`, so
seeding a same-named table would collide with SQLMesh's own managed output
(this actually happened once during the spike — see the `compare` schema
below for the workaround). Production's real `core.venue` was instead copied
into `compare.venue_prod`, purely for tie-out comparison — a legitimate use
of a same-shaped table that just needed a different name.

## Directory layout

Standard `sqlmesh init postgres` scaffold, project at repo root under
`transforms/` (not `sqlmesh/`, to avoid the sibling-of-the-tool-name
confusion; not nested under `mlb_baseball/`, to keep this cleanly separable
from the shipped Python package while the go/no-go is still open).

```
transforms/
  config.yaml              -- postgres gateway -> mlb_spike only
  external_models.yaml      -- schemas for raw/core tables SQLMesh reads but doesn't manage (generated via `sqlmesh create_external_models`)
  models/
    venue.sql               -- core.venue      (raw -> core dimension port)
    park_factor.sql          -- gold.park_factor (ADR-035 port)
    team_woba.sql             -- gold.team_woba   (ADR-036 port)
  audits/
    park_factor_range.sql    -- ported park.py::health_check bound
    team_woba_range.sql      -- ported offense.py::health_check bound
  tests/
    test_venue.yaml           -- unit test (DuckDB), generated via `sqlmesh create_test`
    test_team_woba.yaml        -- unit test (DuckDB), including the window-function/FILTER case
```

## The three ported models

1. **`core.venue`** (`FULL` kind) — port of `conform.py::_build_venues`
   (ADR-030). Simplest of the three: a raw→core dimension build with one
   exact join and one best-effort enrichment join. Chosen as "the simple
   core-layer dimension" over `core.standing` because `core.standing`'s real
   dependency is `core.team.mlb_team_id`'s multi-step, self-bootstrapping
   majority-vote backfill (`_backfill_mlb_team_id` in `conform.py`) — real,
   valuable logic, but a much bigger port than a time-boxed spike needs to
   prove the raw→core shape.

2. **`gold.park_factor`** (`INCREMENTAL_BY_TIME_RANGE`, `time_column
   season_date`) — port of `model/park.py::compute` (ADR-035).

3. **`gold.team_woba`** (`INCREMENTAL_BY_TIME_RANGE`, `time_column
   game_date`) — port of `model/offense.py::compute` (ADR-036).

Both gold models are **deliberately reshaped**, not verbatim ports — see
each model's own docstring for the full reasoning:

- `park_factor`'s production version is *driven by `gold.game_feature`'s own
  demand* (whatever `(venue, season)` pairs that wide feature table asks
  for). `gold.game_feature` itself is out of scope for this spike (we ported
  3 standalone transforms, not the whole feature pipeline), so this version
  instead computes eagerly for every `(venue, season)` with a real completed
  home game — a genuine, standalone dimensional table. The tie-out below
  confirms the actual numbers are unaffected by this shape difference.
- `team_woba`'s production version stores one row per **game** with two
  columns (`home_woba`/`away_woba`). This version stores one row per
  **(game, team)** — the more natural incremental grain, and arguably a
  cleaner dimensional shape (the wide form is one self-join away if a
  downstream consumer needs it).

## Tie-out results

All verified with real queries against both `mlb_spike` and production `mlb`
(read-only). See the session's tool transcript for the exact SQL; summarized
here:

| Check | Expected (ADR / production) | Got (mlb_spike) | Match |
|---|---|---|---|
| 2024 Coors Field park factor | 135.4 (ADR-035 text) | 135.4 | exact |
| 2024 Coors Field park factor | 135.4 (`mlb.gold.game_feature`, live query) | 135.4 | exact |
| 2024 Fenway Park park factor | 116.1 (ADR-035 text) | 116.1 | exact |
| 2024 Fenway Park park factor | 116.1 (`mlb.gold.game_feature`) | 116.1 | exact |
| 2024 park factor rank | Coors #1 | Coors #1 | exact |
| 2023 league-average wOBA | .317 (ADR-036 text) | .317 | exact |
| 2024 team wOBA, all 30 teams | matches production's own full-season aggregate (computed identically against real `mlb`) | byte-identical to production, all 30 teams | exact |
| 2024 team wOBA range | ADR-036 text says ".295-.333" | actual full range is .271 (CHA) – .335 (LAN) | **not an exact match to the ADR's prose — see note below** |
| `gold.team_woba` per-game entering-value, CHA's last 5 2024 home games | `mlb.gold.game_feature.home_woba` for the same `game_id`s | byte-identical (4 decimal places) | exact |
| `core.venue` row count | 260 | 260 | exact |
| `core.venue` column-level parity vs `compare.venue_prod` (via `sqlmesh table_diff`) | — | 248/260 rows (95.4%) full match, 12 partial | see note below |

**Note on the ADR-036 ".295-.333" range**: this spike's numbers are an
*exact* match to production when computed the same way (confirmed both by
the full-season aggregate check and the per-game entering-value check
against real `gold.game_feature` rows) — the discrepancy is in the ADR's own
prose, not in this port. 2024's Chicago White Sox (41-121, the worst
modern-era record) sit at .271, outside the ADR's stated range; the ADR text
says it "spot-checked" 2024 values, not that it checked all 30 teams, and
this specific historic outlier is a plausible thing to have missed in a
spot check. Worth a note back to `docs/DECISIONS.md` ADR-036 independent of
this spike's own conclusion.

**Note on the 12 `core.venue` mismatches**: all 12 are historical parks with
duplicate names in `raw.mlb_venue` (e.g. 15 different "Municipal Stadium"
rows across MLB history, real data, confirmed via `mlb_spike` itself).
`conform.py`'s `UPDATE ... FROM` picks one match non-deterministically when
more than one row matches; this port's `DISTINCT ON` picks the lowest
`mlb_venue_id` deterministically — a real, small, and *already documented in
the model's own docstring before this diff was ever run* behavior
difference. None of the 12 affected parks are relevant to any modern-era
tie-out (Coors/Fenway are both unique matches in `raw.mlb_venue`).

## Exercising SQLMesh's actual selling points

- **Incremental models**: `sqlmesh plan --restate-model gold.team_woba
  --start 2024-01-01 --end 2024-01-31 --auto-apply --no-prompts` recomputed
  *only* that one monthly interval (confirmed in the plan output: "Models
  needing backfill: gold.team_woba: [2024-01-01 - 2024-01-31]"), not the
  full 2021-2026 history. `conform.py`/`park.py`/`offense.py` all
  truncate-and-rebuild their entire output every run — this is the single
  clearest, most concrete win demonstrated in this spike.
  - **Caveat, stated honestly**: the within-season rolling-sum window
    (`ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING`) still has to scan
    that season's *entire* game log to compute correctly, every run — there
    is no cheaper correct way to compute a cumulative sum incrementally in
    pure SQL without either a persisted running total or reprocessing the
    partition. The real win here is "don't rebuild seasons that didn't
    change," not "process only new rows" — still valuable, but a narrower
    claim than "incremental" sometimes implies.

- **Audits**: `park_factor_plausible_range` and `team_woba_plausible_range`
  (both direct ports of the corresponding `health_check()` bounds) run
  automatically as part of `sqlmesh plan`, not a separate `mlb doctor` pass.
  All passed on the full backfill.

- **Unit tests**: `sqlmesh create_test` auto-generates a fixture + expected
  output from a hand-written mock of the model's upstream tables, runs
  against an **in-process DuckDB engine**, not Postgres. Both
  `tests/test_venue.yaml` (regex date parsing, `TO_DATE`/`EXTRACT`, a
  best-effort LEFT JOIN with a genuine no-match case) and
  `tests/test_team_woba.yaml` (a `FILTER (WHERE ...)` aggregate and a
  `WINDOW ... ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING` clause)
  transpiled and ran correctly on the first try — genuinely fast (`sqlmesh
  test` runs both in under a second) and requires no live Postgres. Real
  caveat for the eval: this tests the *transpiled* DuckDB translation of the
  query, not the actual Postgres execution path — a Postgres-specific
  function or edge case that DuckDB's dialect handles differently would
  pass this test and still fail for real. Not observed in this spike (both
  ports' Postgres-specific syntax transpiled correctly), but not a
  logical guarantee either.

- **`sqlmesh table_diff`**: used directly for the `core.venue` tie-out
  above (`sqlmesh table_diff "core.venue:compare.venue_prod" -o
  retro_park_id --skip-grain-check`) — reproduced the same 248/12 split
  found via a hand-written `FULL JOIN`, plus a schema diff and per-column
  match-rate breakdown for free. This is a genuinely better tool for
  ongoing tie-out work than hand-written comparison SQL. Not exercised
  cross-database (against real `mlb` directly) in this spike — that would
  need a second gateway pointed at production, deliberately not set up
  given the read-only-on-prod constraint; the tie-out above instead reused
  plain `SELECT`s against both databases from the same `psql` session.

- **Plan/apply workflow**: `sqlmesh plan --auto-apply --no-prompts`
  demonstrated end to end, including a real bug caught mid-spike (the
  `unique_values` built-in audit checks *each column independently* for
  uniqueness, not the combination — `unique_combination_of_columns` is the
  right audit for a composite grain; the plan step's clear per-model audit
  failure output made this fast to diagnose).

- **Column-level lineage**: no dedicated CLI subcommand in this SQLMesh
  version (0.236.1) — it's exposed through the browser-based `sqlmesh ui`
  (not usable headless) and the Python API (`sqlmesh.core.lineage`). Used
  directly:
  ```python
  from sqlmesh.core.context import Context
  from sqlmesh.core.lineage import column_dependencies

  ctx = Context(paths=".")
  column_dependencies(ctx, "gold.park_factor", "park_factor")
  # -> {'"mlb_spike"."core"."game"': {'away_score', 'home_score'}}
  ```
  Correctly traced `park_factor` back through 4 CTEs to `core.game`'s
  `home_score`/`away_score`, `team_woba`'s `woba` back to
  `raw.retrosheet_event`'s `event_cd`/`ab_fl`/`sf_fl`, and `core.venue`'s
  `mlb_venue_id` back to `raw.mlb_venue.venue_id`. Real capability,
  awkward CLI ergonomics in this version.

## Cleanup

Do not drop `mlb_spike` or any test database from project workflows. The
existing disposable databases are managed outside this repository; tests clean
only the relations they create.
