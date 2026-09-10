## Why

`add-fangraphs-connector` (#173, ADR-288) landed FanGraphs into `raw.fangraphs_*`
— ~715k rows, source-faithful, `local_research` only. Nothing downstream uses
it yet. Two pieces are cheap to surface and genuinely useful for internal
research:

1. **Per-season wOBA / FIP constants.** `mlb_baseball/research.py` documents a
   *single fixed* linear-weight set (`wOBA = 0.69·uBB + 0.72·HBP + 0.89·1B +
   …`). The real weights drift year to year (a 1930 run environment is not a
   1968 one). `raw.fangraphs_guts` carries the full per-season set
   (`woba`, `wobascale`, `wbb`, `whbp`, `w1b`, `w2b`, `w3b`, `whr`, `runsb`,
   `runcs`, `r_pa`, `r_w`, `cfip`) for 156 seasons.
2. **Park factors.** The project has no park-factor relation at all.
   `raw.fangraphs_park_factors` has per-team-season basic and component
   factors (`basic__5yr_`, `n1b`…`hr`, `so`, `bb`, `gb`/`fb`/`ld`, `fip`).
3. **Projections belong in the feature store.** Every preseason / rest-of-season
   system is already snapshotted in `raw.fangraphs_projection` with a
   `_captured_date`. Per ADR-287 the feature/model layer is DuckDB-only, and
   projections are model *inputs*, not research facts — so they conform into a
   `feat.*` relation with as-of retrieval, not `gold`.

Identity is already solved: `core.player.fangraphs_id` (Chadwick register,
migration 0005) and the raw tables' own `xMLBAMID` both join to `core.player`.
No identity work in this change.

## What Changes

- **`gold.fangraphs_guts`** — one row per season, conformed from
  `raw.fangraphs_guts`: numeric-typed columns, `season` as the key, source
  values preserved verbatim (no re-derivation). Built by `mlb report` behind
  the existing `raw.fangraphs_guts` presence pre-check (skips cleanly on a DB
  that never ingested FanGraphs).
- **`gold.fangraphs_park_factors`** — one row per `(season, team)`, `team`
  conformed to `core.team` (FanGraphs' 2–3 letter code → `core.team` via the
  existing team-alias resolution `conform.py` already uses); unresolved team
  codes reported by a health check, never dropped silently. Component factors
  kept as-is.
- **`feat.fangraphs_projection`** (DuckDB, `mlb_baseball/sql/duckdb/`) — one
  row per `(projection_system, stat_group, player_id, captured_date)`,
  `player_id` conformed to `core.player`, built by `mlb build` alongside the
  other `feat.*` relations. `captured_date` is the availability timestamp: a
  projection row is a valid pre-event input only for games on or after it.
  Shaped so a future `get_historical_features`-style call can ask "the
  projection as known on date D".
- **`mlb doctor`** — row-count + `core` join-coverage for each of the three;
  a check that `gold.fangraphs_guts` has a row for every season present in
  `gold.batting_season` from 2002 on (the modern span FanGraphs covers).
- **Docs** — `DATA_DICTIONARY.md` / `TABLE_CONTRACTS.md` gain the three
  relations, each flagged **`local_research` — never `public_safe`, never in
  the published `mlb-research` dataset, never an input to the reference
  baseline model**. `docs/RESEARCH.md` notes that `research.py`'s fixed wOBA
  weights can now be replaced by a `gold.fangraphs_guts` join for
  era-accurate internal work. A new ADR.
- **Rights guard** — `source_profiles` already blocks the `fangraphs`
  connector under any non-`local_research` profile. This change adds: the
  export/serve `RELATIONS` registry must not carry a `public_safe` entry for
  any `gold.fangraphs_*` relation, enforced by a test.

## Capabilities

### New Capabilities

- `fangraphs-conform`: conforming FanGraphs' constants, park factors, and
  projection snapshots from `raw.fangraphs_*` into `core`-joined `gold.*` /
  `feat.*` research relations, `local_research` only, with defined build
  order, idempotency, identity resolution, PIT semantics for projections,
  health checks, and a fail-closed rights posture.

### Modified Capabilities

- None. `statistic-backbone` and `delivery` are untouched — these are new
  internal-research relations, not part of the public backbone.

## Impact

- **New:** `mlb_baseball/sql/gold_fangraphs_guts.sql`,
  `gold_fangraphs_park_factors.sql`,
  `mlb_baseball/sql/duckdb/feat_fangraphs_projection.sql`; wiring in
  `report.py` (`run()` + `health_check()`) and `feat.py` (`_FEATURES` list);
  tests; a `gold` migration for the two `gold.fangraphs_*` tables (or
  `load_dataframe`-style on-demand create, matching how `gold` DDL is done
  elsewhere — decided in design).
- **Modified:** `docs/DATA_DICTIONARY.md`, `docs/TABLE_CONTRACTS.md`,
  `docs/RESEARCH.md`, `docs/DECISIONS.md`, `docs/SOURCE_RIGHTS.md` (note the
  new derived relations inherit the FanGraphs row's `local_research`).
- **Rights:** no new source, no network. Everything derived stays
  `local_research`; the change tightens the export registry so it can't leak.
- **Deliberately deferred** (bigger, mostly cross-validation value — revisit
  when Phase B opens): the full FanGraphs season stat-line conform
  (`gold.fangraphs_batting_season` / `_pitching_season` with WAR / wOBA /
  wRC+ / Stuff+ / PitchingBot), split leaderboards, THE BOARD prospects, and
  a *project-computed* per-season constants table for the publishable path
  (the FanGraphs guts table is a reference/cross-check; a wOBA the project
  publishes must be computed from the project's own `core.play`, not from
  FanGraphs).

## Owner decision embedded here

FanGraphs is `local_research` — it can never ship in the public dataset, so
this is internal-research infrastructure, arguably Phase-B-adjacent. The case
for doing the *reference* slice now anyway: (a) it's small and additive, (b)
per-season constants and park factors are reference data the same shape as the
backbone's other lookups, not "the Engine", (c) `research.py` already wants
era-accurate weights and currently fakes them. If the owner would rather hold
all FanGraphs-derived work until Phase B formally opens, the projection slice
(`feat.fangraphs_projection`) alone is the minimum — it's a pure model-input
relation with a concrete near-term consumer (the walk-forward harness).
