## Why

`add-fangraphs-connector` (#173, ADR-288) landed FanGraphs into `raw.fangraphs_*`
— source-faithful, `local_research` only. Nothing downstream uses it yet. This
change is **Beat 1**: two reference lookups that are cheap to surface and
genuinely useful for internal research.

1. **Per-season wOBA / FIP constants.** `mlb_baseball/research.py` documents a
   *single fixed* linear-weight set (`wOBA = 0.69·uBB + 0.72·HBP + 0.89·1B +
   …`). The real weights drift year to year (a 1930 run environment is not a
   1968 one). `raw.fangraphs_guts` carries the full per-season set
   (`woba`, `wobascale`, `wbb`, `whbp`, `w1b`, `w2b`, `w3b`, `whr`, `runsb`,
   `runcs`, `r_pa`, `r_w`, `cfip`) for the whole of FanGraphs' Guts! history.
2. **Park factors.** The project has no park-factor reference relation at all.
   `raw.fangraphs_park_factors` has per-team-season basic and component
   factors (`basic__5yr_`, `n1b`…`hr`, `so`, `bb`, `gb`/`fb`/`ld`, `fip`).

Identity: `gold.fangraphs_guts` needs none (keyed on `season`).
`gold.fangraphs_park_factors` resolves FanGraphs' team *nickname* to `core.team`
through a new `'fangraphs'` block in `core.team_alias` — the project's one
team-code resolution point.

## What Changes

- **`gold.fangraphs_guts`** — one row per season, conformed from
  `raw.fangraphs_guts`: numeric-typed columns, `season` as the key, source
  values preserved verbatim (no re-derivation, no interpolation). Built by
  `mlb report` behind the existing `raw.fangraphs_guts` presence pre-check
  (skips cleanly on a DB that never ingested FanGraphs).
- **`gold.fangraphs_park_factors`** — one row per `(season, team_id)`,
  **scoped `season >= 2003`**. `team` (a FanGraphs nickname) conformed to
  `core.team` via `core.team_alias`; a nickname with no alias produces no row
  and is surfaced by a health check, never dropped silently or guessed.
  Component factors kept as published. Pre-2003 rows stay in `raw` (low value,
  unstable franchise set).
- **Migration `0104_gold_fangraphs_reference.sql`** — creates both tables
  (additive; rollback = `DROP TABLE`) and swaps `core.team_alias`'s
  single-column `UNIQUE(alias)` for `UNIQUE(alias, source)` (the correct key
  for a multi-source alias crosswalk — FanGraphs shares the strings
  `"Athletics"` / `"Rays"` with the existing `'rebrand'` block).
- **`conform.py::_TEAM_ALIAS_SEED`** — a `'fangraphs'` source block, 34
  nickname→`retro_team_id` entries verified against the real distinct `team`
  values in `raw.fangraphs_park_factors` (CLE / TBA / WAS each carry multiple
  historically-accurate nicknames).
- **`mlb doctor`** — for each lookup: row count / presence, `core.team`
  join-coverage for park factors, and a check that `gold.fangraphs_guts` has a
  row for every `gold.batting_season` season from 2003 on. All no-op cleanly on
  a FanGraphs-free database.
- **Docs** — `DATA_DICTIONARY.md` / `TABLE_CONTRACTS.md` gain the two
  relations, each flagged **`local_research` — never `public_safe`, never in
  the published `mlb-research` dataset, never an input to the reference
  baseline model**. `docs/RESEARCH.md` notes that `research.py`'s fixed wOBA
  weights can now be replaced by a `gold.fangraphs_guts` join for era-accurate
  *internal* work (a follow-up change; `research.py` is not touched here).
  `docs/SOURCE_RIGHTS.md` records that the derived relations inherit the
  FanGraphs row's `local_research`. A new ADR (ADR-290).
- **Rights guard** — `source_profiles` already blocks the `fangraphs`
  connector under any non-`local_research` profile. This change adds a standing
  test: nothing in `export.RELATIONS` whose name begins `gold.fangraphs_` may
  carry a `public_safe` profile. (`serve.py` has no relation registry.)

## Deferred — Beat 2: `feat.fangraphs_projection`

Every preseason / rest-of-season projection system is already snapshotted in
`raw.fangraphs_projection` with a `_captured_date`. Conforming it into a DuckDB
`feat.*` relation with as-of (`captured_date`) retrieval is **explicitly held
back to Beat 2**, for three reasons:

1. Doing it now would bake a **can-never-ship** (`local_research`) dependency
   into the walk-forward harness's public contract while that interface is
   still being set.
2. `feat.*` is rebuilt by `mlb build`, which **ships as code**, so
   `feat.fangraphs_projection` is *local-by-construction*, not automatically
   *internal-only* — a deliberate rights-profile decision Beat 2 must make, not
   inherit.
3. Once the harness has a register-a-forecaster interface, projections plug in
   cleanly as an **optional forecaster**, not a built-in.

## Also deferred (Phase B / separate changes)

The full FanGraphs season stat-line conform (`gold.fangraphs_batting_season` /
`_pitching_season` with WAR / wOBA / wRC+ / Stuff+ / PitchingBot), split
leaderboards, THE BOARD prospects, and a *project-computed* per-season constants
table for the publishable path (the FanGraphs Guts! table is a
reference/cross-check; a wOBA the project publishes must be computed from
`core.play`, not from FanGraphs).

## Capabilities

### New Capabilities

- `fangraphs-conform`: conforming FanGraphs' Guts! constants and park factors
  from `raw.fangraphs_*` into `core`-joined `gold.*` reference lookups,
  `local_research` only, with defined build order, idempotency, identity
  resolution, `season >= 2003` park-factor scope, health checks, and a
  fail-closed rights posture. Projections are a named Beat 2 deferral.

### Modified Capabilities

- None. `statistic-backbone` and `delivery` are untouched — these are new
  internal-research reference relations, not part of the public backbone.

## Impact

- **New:** `migrations/0104_gold_fangraphs_reference.sql`,
  `mlb_baseball/sql/gold_fangraphs_guts.sql`,
  `mlb_baseball/sql/gold_fangraphs_park_factors.sql`; wiring in `report.py`
  (`run()` + `health_check()`); a `'fangraphs'` block in
  `conform.py::_TEAM_ALIAS_SEED`; tests
  (`tests/integration/test_report_fangraphs_guts.py`,
  `test_report_fangraphs_park_factors.py`, additions to `test_conform.py`,
  `tests/unit/test_fangraphs_conform_rights.py`).
- **Modified:** `docs/DATA_DICTIONARY.md`, `docs/TABLE_CONTRACTS.md`,
  `docs/RESEARCH.md`, `docs/DECISIONS.md`, `docs/SOURCE_RIGHTS.md`;
  `tests/integration/test_conform.py` (team-alias count assertions grow by the
  one ATL FanGraphs nickname).
- **Rights:** no new source, no network. Everything derived stays
  `local_research`; the change tightens the export registry so it can't leak.
- **Schema:** `core.team_alias` gains `UNIQUE(alias, source)` in place of
  `UNIQUE(alias)` — a superset, no existing insert path relies on the
  single-column form.

## Owner decision embedded here

FanGraphs is `local_research` — it can never ship in the public dataset, so
this is internal-research infrastructure, arguably Phase-B-adjacent. The case
for doing the *reference* slice now: (a) it's small and additive, (b)
per-season constants and park factors are reference data the same shape as the
backbone's other lookups, not "the Engine", (c) `research.py` already wants
era-accurate weights and currently fakes them. Projections
(`feat.fangraphs_projection`) are the deliberate Beat 2 deferral above.
