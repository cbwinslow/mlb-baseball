## Context

See `proposal.md` — Why. `raw.fangraphs_*` is landed (#173) and unused. This
change is **Beat 1** — the two `gold` reference lookups only. Relevant current
state:

- `gold.*` tables are created by **numbered migrations**
  (`migrations/0094_gold_batting_game.sql`, `0098_gold_career.sql`, …). The
  build SQL in `mlb_baseball/sql/*.sql` `TRUNCATE`s (via the caller) and
  re-`INSERT`s; it does not `CREATE`.
- `report.run()` calls `_build_backbone_relation(conn, table, sql, source=…)`
  which pre-checks the source `to_regclass`, skips on absence, else `TRUNCATE`
  + build inside a savepoint. `health_check()` returns a flat `list[Check]`.
- Team-code resolution: `core.team_alias` (migration 0009) seeded by
  `conform.py::_TEAM_ALIAS_SEED` / `_build_team_aliases`. The existing seed
  has two vocabularies: Kalshi ticker codes and three rebrand names.
- `raw.fangraphs_guts` columns (all text): `season, woba, wobascale, wbb,
  whbp, w1b, w2b, w3b, whr, runsb, runcs, r_pa, r_w, cfip` (+ `_loaded_at`).
- `raw.fangraphs_park_factors` (all text): `season, team, basic__5yr_, n3yr,
  n1yr, n1b, n2b, n3b, hr, so, bb, gb, fb, ld, iffb, fip` (+ `_season`,
  `_loaded_at`). `team` is a FanGraphs **nickname**, historically accurate
  (CLE "Indians"/"Cleveland"/"Guardians"; TBA "Devil Rays"/"Rays"; WAS
  "Expos"/"Nationals"). Span 1901–2026.
- `docs/SOURCE_RIGHTS.md` — "FanGraphs via fungo … local research: yes,
  owner-risk. public-safe: no." `require_sources` fails closed for everything
  outside `public_safe` (Retrosheet-only).

## Goals / Non-Goals

**Goals:**

- Two reference lookups conformed from `raw.fangraphs_*`, `core`-joined where
  relevant, built by the existing `mlb report` flow, idempotent, skip-clean
  without the raw source.
- Park factors scoped `season >= 2003`.
- A fail-closed rights guard: no `gold.fangraphs_*` can be marked
  `public_safe`, enforced by a test.

**Non-Goals:**

- `feat.fangraphs_projection` — the deliberate **Beat 2** deferral (see
  proposal). No DuckDB / `feat.py` change in this beat.
- The full FanGraphs season stat-line conform (WAR / wOBA / wRC+ / Stuff+ /
  PitchingBot), splits, THE BOARD prospects — Phase B.
- A project-computed per-season constants table for the *publishable* wOBA
  path — separate change; this one only surfaces FanGraphs' as a reference.
- Replacing `research.py`'s hardcoded weights (a follow-up once
  `gold.fangraphs_guts` exists and callers are audited).
- Any new source, network call, or paid dependency.

## Decisions

### D1: migration + build SQL, same shape as every other `gold` relation

One numbered migration (`0104_gold_fangraphs_reference.sql`) creates both
tables: `gold.fangraphs_guts` (`season integer PRIMARY KEY`, then the 13
constants `numeric`); `gold.fangraphs_park_factors` (`season integer`,
`team_id bigint REFERENCES core.team(id)`, then 14 factors `numeric`,
`PRIMARY KEY (season, team_id)`). `COMMENT ON TABLE` on both carries the
`local_research` / reference-only banner. Two build files
(`gold_fangraphs_guts.sql`, `gold_fangraphs_park_factors.sql`) are a single
`INSERT … SELECT` with `NULLIF(x,'')::numeric` casts — no leading `TRUNCATE`
(the caller does it), no per-season bind parameter (every season, like the
career builders). Wired into `report.run()` via `_build_backbone_relation`.

- **Alternative — one wide `gold.fangraphs_constants` table:** rejected, the
  two have different grains (season vs season-team).
- **Alternative — `meta.` schema:** rejected, `meta` is lineage/registry;
  these are research lookups consumed like `gold`.

### D2: park-factor team resolution — extend `core.team_alias`

Add a `'fangraphs'` source block to `conform.py::_TEAM_ALIAS_SEED` — 34
nickname→`retro_team_id` entries verified against the real distinct `team`
values in `raw.fangraphs_park_factors`. `gold_fangraphs_park_factors.sql`
joins `raw … JOIN core.team_alias a ON a.source='fangraphs' AND
lower(a.alias)=lower(pf.team) JOIN core.team t ON t.id=a.team_id`. An
unresolved nickname produces no row and is surfaced by the health check.

`core.team_alias`'s `UNIQUE(alias)` (migration 0009, from when only two
disjoint market vocabularies existed) becomes `UNIQUE(alias, source)` in
migration 0104 — the correct key for a multi-source crosswalk, and required
because FanGraphs shares `"Athletics"` / `"Rays"` with the `'rebrand'` block.
`_team_lookup` (markets) builds an `{alias: team_id}` dict with last-write-wins
and is unaffected (the shared strings map to the same team).

- **Alternative — hardcode the map in the build SQL:** rejected, `team_alias`
  is the project's one team-code resolution point.
- **Alternative — keep `UNIQUE(alias)`, skip the two shared strings:**
  rejected, then OAK / TBA park factors would silently not resolve under
  `a.source='fangraphs'`.

### D3: park factors scoped `season >= 2003`

Pre-2003 FanGraphs park factors are low value and the franchise set is
unstable (relocations, expansion). The build's `WHERE NULLIF(pf.season,'')
::integer >= 2003` is the scope line; pre-2003 rows stay in `raw`, documented
as deferred. The 2003+ franchise set is fully covered by the 34-alias seed, so
the park-factor join-coverage health check compares conformed rows against
*every* 2003+ raw row — a shortfall is an unresolved nickname.

### D4: rights guard — a test over the export registry

`mlb_baseball/export.py` holds `RELATIONS: tuple[ExportRelation, …]`, each
with a `profile` field and a `qualified_name` property.
`tests/unit/test_fangraphs_conform_rights.py` asserts no relation whose
`qualified_name` starts `gold.fangraphs_` has `profile == "public_safe"`, that
none appears in `export.BACKBONE_CANDIDATES`, and that `require_sources(
"public_safe", ["fangraphs"], …)` still raises `SourceProfileError`. No code
path *adds* a `public_safe` entry — the test is a standing guard.
`mlb_baseball/serve.py` has no relation registry.

### D5: `research.py` weights — noted, not changed here

`research.py`'s `wOBA = 0.69·uBB + …` string stays. A follow-up (its own
change) audits every consumer of a fixed weight and switches internal /
non-published paths to a `gold.fangraphs_guts` join. Doing it here would
balloon the diff and risk a published figure silently picking up
FanGraphs-sourced constants.

### D6: projections — Beat 2, deliberately

See proposal "Deferred — Beat 2". Building `feat.fangraphs_projection` now
would set a `local_research` dependency into the walk-forward harness's public
contract before that interface exists; `feat.*` ships as code so the relation
is local-by-construction, not automatically internal-only; and a
register-a-forecaster interface makes projections a clean optional plug-in
later. Beat 2 owns the rights-profile decision.

## Risks / Trade-offs

- **[Phase-A vs Phase-B]** FanGraphs is internal-only, so this is
  research-*infrastructure*. → The `gold` slice is reference data (constants,
  park factors) the same shape as the backbone's other lookups; projections
  are the explicit Beat 2 deferral.
- **[Constants misuse]** Someone joins `gold.fangraphs_guts` into a published
  wOBA. → Column/table comments and `TABLE_CONTRACTS.md` state
  "reference / cross-check only"; the rights test blocks the export path; a
  project-computed constants table is the named follow-up.
- **[FanGraphs nickname drift / historical clubs]** A relocated-franchise
  nickname (e.g. a future rebrand) may not resolve. → The join-coverage health
  check reports it; `_TEAM_ALIAS_SEED` is the one place to fix it; no silent
  null-team row. Scoping to `season >= 2003` bounds the franchise set.
- **[`core.team_alias` constraint change]** `UNIQUE(alias)` →
  `UNIQUE(alias, source)`. → A strict superset; the market `_team_lookup` dict
  and every existing insert path are unaffected; rollback restores the old
  constraint.

## Migration Plan

1. `migrations/0104_gold_fangraphs_reference.sql`: `CREATE TABLE`
   `gold.fangraphs_guts` + `gold.fangraphs_park_factors`; swap the
   `core.team_alias` unique constraint. Additive; rollback drops the two
   tables and restores `UNIQUE(alias)`.
2. Build files + `report.py` wiring + `conform.py` alias seed + tests + docs +
   ADR. All behind the raw-source pre-check, so a FanGraphs-free database is
   unaffected.
3. Owner runs `mlb migrate` + `mlb report` on production once merged. Verify:
   `gold.fangraphs_guts` row count ≈ FanGraphs Guts! history; one
   `gold.fangraphs_park_factors` row per (season ≥ 2003, resolvable team);
   `mlb doctor` green; a spot wOBA recompute for one modern season matches
   FanGraphs within rounding.
- **Rollback:** drop the two `gold` tables, restore the `core.team_alias`
  constraint, remove the `report.py` wiring and the `'fangraphs'` alias block.
  `raw.fangraphs_*` untouched.

## Open Questions

- None blocking. Beat 2 (`feat.fangraphs_projection`) will decide whether the
  projection feature relation carries the connector's `_row_hash` and what
  rights profile a `feat.*` relation declares.
