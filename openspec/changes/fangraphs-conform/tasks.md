## 1. Migration: the two `gold.fangraphs_*` tables

- [x] 1.1 `migrations/0104_gold_fangraphs_reference.sql` — `CREATE TABLE gold.fangraphs_guts` (`season int PRIMARY KEY`, `woba/wobascale/wbb/whbp/w1b/w2b/w3b/whr/runsb/runcs/r_pa/r_w/cfip numeric`) and `gold.fangraphs_park_factors` (`season int`, `team_id bigint REFERENCES core.team(id)`, `basic_5yr/pf_3yr/pf_1yr/pf_1b/pf_2b/pf_3b/pf_hr/pf_so/pf_bb/pf_gb/pf_fb/pf_ld/pf_iffb/pf_fip numeric`, `PRIMARY KEY (season, team_id)`). `COMMENT ON TABLE` both with the **`local_research` only — never public_safe / published / a baseline-model input; `gold.fangraphs_guts` is a cross-check, a publishable wOBA/FIP is computed from core.play** banner. Swap `core.team_alias`'s `UNIQUE(alias)` for `UNIQUE(alias, source)`. Additive; rollback = `DROP TABLE` + restore `UNIQUE(alias)`. Verify: `mlb migrate` on a scratch DB applies it; `\d` shows both tables and the composite constraint; the pytest migrate picks it up.

## 2. `gold.fangraphs_guts` builder

- [x] 2.1 `mlb_baseball/sql/gold_fangraphs_guts.sql` — one `INSERT … SELECT NULLIF(x,'')::numeric … FROM raw.fangraphs_guts` (no leading `TRUNCATE`, no per-season bind — every season, like the career builders). Verify: `sqlfluff` clean; an integration test that a seeded `raw.fangraphs_guts` fixture maps 1:1 (values preserved, cast to numeric).
- [x] 2.2 Wire into `report.run()` via `_build_backbone_relation(conn, "gold.fangraphs_guts", _GOLD_FANGRAPHS_GUTS_SQL, source="raw.fangraphs_guts")`. Verify: with `raw.fangraphs_guts` absent the call returns 0 and raises nothing (and does not TRUNCATE a pre-seeded gold row); with a seeded fixture it builds and re-builds to the same rows.

## 3. `gold.fangraphs_park_factors` builder + team resolution

- [x] 3.1 `conform.py::_TEAM_ALIAS_SEED` — a `'fangraphs'` source block, 34 nickname→`retro_team_id` entries, verified against the real distinct `team` values in `raw.fangraphs_park_factors` (CLE / TBA / WAS each carry multiple historically-accurate nicknames). Verify: `test_conform.py` — every one of the 34 aliases resolves to exactly one `core.team`; the existing team-alias count assertions are updated for the one extra ATL nickname.
- [x] 3.2 `mlb_baseball/sql/gold_fangraphs_park_factors.sql` — `raw.fangraphs_park_factors` JOIN `core.team_alias` (`source='fangraphs'`, `lower(alias)=lower(team)`) JOIN `core.team`; one row per `(season, team_id)`; `WHERE NULLIF(pf.season,'')::integer >= 2003`; factors cast `numeric`. A nickname that does not resolve is not written. Verify: fixture with a resolvable + an unresolvable nickname → one row + the coverage check red; a pre-2003 row → no row; `sqlfluff` clean.
- [x] 3.3 Wire into `report.run()` (same helper, `source="raw.fangraphs_park_factors"`). Verify: skip-clean without the raw table; idempotent with it.

## 4. `mlb doctor` checks

- [x] 4.1 `report.health_check()` — for each lookup (appended only when its `raw.fangraphs_*` source is present, so a FanGraphs-free DB is unchanged): `gold.fangraphs_guts` has rows; every `gold.batting_season` season `>= 2003` has a `gold.fangraphs_guts` row; `gold.fangraphs_park_factors` row count equals every `raw.fangraphs_park_factors` row for `season >= 2003` (a shortfall = an unresolved nickname; an over-count = alias fan-out). Verify: `test_report_fangraphs_park_factors.py` — a seeded unresolvable nickname turns the coverage check red; all checks no-op on a DB without the FanGraphs raw tables.

## 5. Rights guard

- [x] 5.1 `tests/unit/test_fangraphs_conform_rights.py` — assert no relation in `export.RELATIONS` whose `qualified_name` starts `gold.fangraphs_` has `profile == "public_safe"`, none is in `export.BACKBONE_CANDIDATES`, and `require_sources("public_safe", ["fangraphs"], purpose="test")` raises `SourceProfileError` naming the source and `docs/SOURCE_RIGHTS.md`. (`serve.py` has no relation registry.) Verify: the test passes now and would fail if a `public_safe` entry were added.

## 6. Docs

- [x] 6.1 `docs/DATA_DICTIONARY.md` + `docs/TABLE_CONTRACTS.md` — the two relations: grain, source, null policy, `season >= 2003` scope for park factors, and the **`local_research` — never public_safe / published / baseline-model input; `gold.fangraphs_guts` is a reference/cross-check, publishable wOBA is computed from `core.play`** banner. `docs/RESEARCH.md` — the fixed `research.py` weights can be replaced by a `gold.fangraphs_guts` join for internal era-accurate work (follow-up change). `docs/SOURCE_RIGHTS.md` — the derived relations inherit the FanGraphs row's `local_research`. `docs/DECISIONS.md` — ADR-290 (FanGraphs Guts! constants + park factors → `gold` reference lookups, `local_research`; projections deferred to Beat 2; full stat-line conform deferred). Verify: `grep` the new table/column names across `docs/` leaves nothing stale; `openspec validate fangraphs-conform --strict` passes.
- [ ] 6.2 Sync the delta into `openspec/specs/fangraphs-conform/spec.md` on archive. Verify: `openspec validate --all` after a dry archive.

## 7. Verification (owner-run against production)

- [ ] 7.1 `mlb migrate` + `mlb report` on production `mlb`. Verify: `gold.fangraphs_guts` row count ≈ FanGraphs Guts! history; `gold.fangraphs_park_factors` ~30/modern-season for `season >= 2003`; `mlb doctor` green; a hand wOBA recompute for one 2015 batter using `gold.fangraphs_guts` weights matches FanGraphs' published wOBA within 0.001.
- [ ] 7.2 Confirm no `gold.fangraphs_*` appears in a `mlb export --profile public_safe` bundle (impossible by the guard; verify anyway).

## 8. Deferred — Beat 2

- [ ] 8.1 `feat.fangraphs_projection` (DuckDB `feat.*`, `captured_date` as the as-of key) is **not** in this beat. Beat 2 owns it — and the rights-profile decision for a `feat.*` relation that is local-by-construction but ships as code. See `proposal.md` "Deferred — Beat 2".
