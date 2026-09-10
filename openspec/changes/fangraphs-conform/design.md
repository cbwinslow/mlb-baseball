## Context

See `proposal.md` — Why. `raw.fangraphs_*` is landed (#173) and unused.
Relevant current state:

- `gold.*` tables are created by **numbered migrations**
  (`migrations/0094_gold_batting_game.sql`, `0098_gold_career.sql`, …). The
  build SQL in `mlb_baseball/sql/*.sql` `TRUNCATE`s and re-`INSERT`s; it does
  not `CREATE`.
- `report.run()` calls `_build_backbone_relation(conn, table, sql, source=…)`
  which pre-checks the source `to_regclass`, skips on absence, else
  `TRUNCATE` + build inside a savepoint. `_build_backbone_relation_multi`
  (added in #177) is the two-source variant. `health_check()` returns a flat
  `list[Check]`.
- `feat.*` is DuckDB-only (ADR-287). `mlb_baseball/feat.py` runs the ordered
  `_FEATURES` list — DuckDB-dialect files in `mlb_baseball/sql/duckdb/`
  against a Postgres DB `ATTACH`ed `READ_ONLY` as `pg`, with build params
  passed as DuckDB session variables. `feat_player_form.sql` is the template:
  an `event_ts` clock column carries the point-in-time ordering.
- Team-code resolution: `core.team_alias` (migration 0009) seeded by
  `conform.py::_build_team_aliases`, plus ad-hoc joins on
  `core.team.retro_team_id`. FanGraphs' team codes (`NYY`, `SDP`, `TBR`, …)
  are close to but not identical to Retrosheet's (`NYA`, `SDN`, `TBA`).
- `core.player.fangraphs_id` exists (migration 0005); the raw FanGraphs tables
  also carry `xMLBAMID`, which joins `core.player.mlbam_id` directly.
- `raw.fangraphs_guts` columns: `season, woba, wobascale, wbb, whbp, w1b, w2b,
  w3b, whr, runsb, runcs, r_pa, r_w, cfip` (all text). 156 rows.
- `raw.fangraphs_park_factors`: `season, team, basic__5yr_, n3yr, n1yr, n1b,
  n2b, n3b, hr, so, bb, gb, fb, ld, iffb, fip` (+ `_season`/`_loaded_at`).
- `raw.fangraphs_projection`: 120 cols incl. `playerid`, `xMLBAMID`,
  `_projection_system`, `_stat_group`, `_horizon`, `_captured_date`,
  `_row_hash`.
- `docs/SOURCE_RIGHTS.md` — "FanGraphs via fungo … local research: yes,
  owner-risk. public-safe: no." `source_profiles.PUBLIC_SAFE` is
  Retrosheet-only; `require_sources` fails closed for everything else.

## Goals / Non-Goals

**Goals:**

- Three relations conformed from `raw.fangraphs_*`, `core`-joined, built by
  the existing `mlb report` / `mlb build` flows, idempotent, skip-clean
  without the raw source.
- A fail-closed rights guard: no `gold.fangraphs_*` can be marked
  `public_safe`, enforced by a test.
- Projections into `feat.*` with a real as-of column (ADR-287, owner's answer).

**Non-Goals:**

- The full FanGraphs season stat-line conform (WAR / wOBA / wRC+ / Stuff+ /
  PitchingBot), splits, THE BOARD prospects — deferred to Phase B.
- A project-computed per-season constants table for the *publishable* wOBA
  path — separate change; this one only surfaces FanGraphs' as a reference.
- Replacing `research.py`'s hardcoded weights in this change (a follow-up once
  `gold.fangraphs_guts` exists and callers are audited).
- Any new source, network call, or paid dependency.
- Touching the public statistic backbone, `delivery`, or the reference model.

## Decisions

### D1: `gold.fangraphs_guts` / `gold.fangraphs_park_factors` — migration + build SQL, same as every other `gold` relation

One numbered migration creates both tables (numeric-typed columns, `season`
PK on guts, `(season, team_id)` PK on park factors, column comments carrying
the `local_research` flag). Two build files
(`mlb_baseball/sql/gold_fangraphs_guts.sql`, `gold_fangraphs_park_factors.sql`)
`TRUNCATE` + `INSERT … SELECT` with `NULLIF(x,'')::numeric` casts. Wired into
`report.run()` via `_build_backbone_relation(conn, "gold.fangraphs_guts",
_SQL, source="raw.fangraphs_guts")` — the existing helper already gives
skip-on-absent + idempotency + savepoint isolation for free.

- **Alternative — a single `gold.fangraphs_constants` wide table:** rejected,
  the two have different grains (season vs season-team).
- **Alternative — `meta.` schema:** rejected, `meta` is lineage/registry;
  these are research lookups consumed like `gold`.

### D2: Park-factor team resolution — extend `core.team_alias`, don't invent a second mechanism

`conform.py::_build_team_aliases` already seeds `core.team_alias`. Add the
FanGraphs code set there (verified against real `raw.fangraphs_park_factors`
values, not guessed — the ~7 that differ from Retrosheet: `NYY→NYA`,
`SDP→SDN`, `TBR→TBA`, `KCR→KCA`, `CHW→CHA`, `SFG→SFN`, `WSN→WAS`, plus the
historical relocations FanGraphs may or may not carry). `gold_fangraphs_park_factors.sql`
joins `raw … JOIN core.team_alias a ON lower(a.alias)=lower(pf.team) AND
a.source='fangraphs' JOIN core.team t ON t.id=a.team_id`. An unresolved code
produces no row and is surfaced by the health check.

- **Alternative — hardcode the map in the build SQL:** rejected, `team_alias`
  is the project's one team-code resolution point (`conform.py` comment).

### D3: `feat.fangraphs_projection` — DuckDB `feat.*`, `captured_date` as the PIT key

New `mlb_baseball/sql/duckdb/feat_fangraphs_projection.sql`, appended to
`feat.py::_FEATURES` after `feat.game`. Reads
`pg.raw.fangraphs_projection` (the ATTACHed Postgres), joins
`pg.core.player` on `xMLBAMID = mlbam_id` (falls back to
`playerid = fangraphs_id`), emits one row per `(_projection_system,
_stat_group, player_id, _captured_date)` with the projected stat columns and
`_horizon`. `_captured_date` is kept as `captured_date DATE` — the as-of key.
No `event_ts` fiction needed (projections already carry a real date); an
`ASOF JOIN` on `captured_date <= target_date` is the intended retrieval shape.
`feature_version` session var tags the rows like the other `feat.*` files.

- The relation is rebuilt whole each `mlb build` from the current
  `raw.fangraphs_projection` snapshots (which only grow — the connector's
  change-detection append). Idempotent by construction.
- Retrieval helper (an `feat.fangraphs_projection` reader in `mlb-research`
  shaped like `get_historical_features`) is **out of scope here** — this
  change builds the relation; a consumer wires the retrieval when the
  walk-forward harness needs it.

### D4: Rights guard — a test over the export/serve registry

`mlb_baseball/export.py` / `serve.py` hold a `RELATIONS` registry with a
`profile` per relation. Add a unit test:
`{r.qualified_name for r in RELATIONS if r.profile == "public_safe"}` contains
nothing matching `gold.fangraphs_*`, and `require_sources("public_safe",
["fangraphs"], …)` still raises. Document in `docs/SOURCE_RIGHTS.md` that the
derived relations inherit the FanGraphs row. No code path *adds* a
`public_safe` entry in this change — the test is a standing guard against a
future one.

### D5: `research.py` weights — noted, not changed here

`research.py`'s `wOBA = 0.69·uBB + …` string stays. A follow-up (its own
change) audits every consumer of a fixed weight and switches internal /
non-published paths to a `gold.fangraphs_guts` join. Doing it here would
balloon the diff and risks a published figure silently picking up
FanGraphs-sourced constants.

## Risks / Trade-offs

- **[Phase-A vs Phase-B]** FanGraphs is internal-only, so this is
  research-*infrastructure*, not the public database. → The `gold` slice is
  reference data (constants, park factors) the same shape as the backbone's
  other lookups; the proposal puts the go/no-go and the "projections-only
  minimum" explicitly to the owner.
- **[Constants misuse]** Someone joins `gold.fangraphs_guts` into a published
  wOBA. → The relation's column comments and `TABLE_CONTRACTS.md` state
  "reference / cross-check only"; the rights test blocks the export path; a
  project-computed constants table is the named follow-up.
- **[FanGraphs team codes drift / historical clubs]** A relocated-franchise
  code (`MON`, `ANA`, `FLA`) may not resolve. → Health check reports it;
  `team_alias` is the one place to fix it; no silent null-team row.
- **[Projection snapshot growth in DuckDB]** `raw.fangraphs_projection` grows
  with every capture; `feat.fangraphs_projection` mirrors it. → It's DuckDB
  (columnar, cheap), rebuilt not appended, and the connector's own
  change-detection already bounds the raw growth. Revisit a retention window
  if it matters (same open question the connector's sidecar carries).
- **[`xMLBAMID` blank for a debutant]** The register lags for a first-year
  player. → Fall back to `playerid = fangraphs_id`; an unresolved row is a
  health-check shortfall, not a silent drop.

## Migration Plan

1. One `gold` migration: `CREATE TABLE gold.fangraphs_guts` +
   `gold.fangraphs_park_factors`. Additive; rollback is `DROP TABLE`.
2. Build files + `report.py` / `feat.py` wiring + `conform.py` team-alias
   seed + tests + docs + ADR. All behind the raw-source pre-check, so a
   FanGraphs-free database is unaffected.
3. Owner runs `mlb migrate` + `mlb report` + `mlb build` on production once
   merged (same shape as the backbone-2026 task 9). Verify: row counts,
   `mlb doctor` green, a spot wOBA recompute for one modern season matches
   FanGraphs within rounding.
- **Rollback:** drop the two `gold` tables, remove `feat.fangraphs_projection`
  from `_FEATURES`, revert the wiring. `raw.fangraphs_*` untouched.

## Open Questions

- Whether `feat.fangraphs_projection` should also carry the connector's
  `_row_hash` (lets a consumer detect "same projection, re-snapshotted" vs a
  real move without re-hashing). Cheap to include; leaning yes. Does not
  change the grain or the spec.
