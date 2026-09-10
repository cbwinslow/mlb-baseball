## 1. Migration: the two `gold.fangraphs_*` tables

- [ ] 1.1 `migrations/NNNN_gold_fangraphs_reference.sql` — `CREATE TABLE gold.fangraphs_guts` (`season int PRIMARY KEY`, `woba/wobascale/wbb/whbp/w1b/w2b/w3b/whr/runsb/runcs/r_pa/r_w/cfip numeric`) and `gold.fangraphs_park_factors` (`season int`, `team_id bigint REFERENCES core.team(id)`, `basic_5yr/pf_3yr/pf_1yr/pf_1b/pf_2b/pf_3b/pf_hr/pf_so/pf_bb/pf_gb/pf_fb/pf_ld/pf_iffb/pf_fip numeric`, `PRIMARY KEY (season, team_id)`). Column comments carry **`local_research` only — never public_safe / published / a baseline-model input**. Verify: `mlb migrate` on a scratch DB applies it; `\d` shows both; the pytest migrate picks it up.

## 2. `gold.fangraphs_guts` builder

- [ ] 2.1 `mlb_baseball/sql/gold_fangraphs_guts.sql` — `TRUNCATE gold.fangraphs_guts; INSERT … SELECT NULLIF(x,'')::numeric … FROM raw.fangraphs_guts`. One statement, no `%(season)s` (all seasons, like the career builders). Verify: `sqlfluff` clean; a unit-style test that a captured `raw.fangraphs_guts` fixture maps 1:1 (values preserved, cast to numeric).
- [ ] 2.2 Wire into `report.run()` via `_build_backbone_relation(conn, "gold.fangraphs_guts", _GOLD_FANGRAPHS_GUTS_SQL, source="raw.fangraphs_guts")`. Verify: `test_report.py` — with `raw.fangraphs_guts` absent the call returns 0 and raises nothing; with a seeded fixture it builds and re-builds to the same rows.

## 3. `gold.fangraphs_park_factors` builder + team resolution

- [ ] 3.1 `conform.py::_build_team_aliases` — add the FanGraphs code set to `core.team_alias` with `source='fangraphs'`, verified against the real distinct `team` values in `raw.fangraphs_park_factors` (not guessed). Verify: `test_conform.py` — every distinct 2026 `raw.fangraphs_park_factors.team` resolves to exactly one `core.team`.
- [ ] 3.2 `mlb_baseball/sql/gold_fangraphs_park_factors.sql` — `raw.fangraphs_park_factors` JOIN `core.team_alias` (`source='fangraphs'`) JOIN `core.team`; one row per `(season, team_id)`; component factors cast `numeric`. A row whose `team` does not resolve is not written. Verify: fixture with one resolvable + one unresolvable team → one row; `sqlfluff` clean.
- [ ] 3.3 Wire into `report.run()` (same helper, `source="raw.fangraphs_park_factors"`). Verify: skip-clean without the raw table; idempotent with it.

## 4. `feat.fangraphs_projection` (DuckDB feature store)

- [ ] 4.1 `mlb_baseball/sql/duckdb/feat_fangraphs_projection.sql` — DuckDB dialect, reads `pg.raw.fangraphs_projection`, joins `pg.core.player` on `xMLBAMID = mlbam_id` with a `playerid = fangraphs_id` fallback; one row per `(_projection_system, _stat_group, player_id, _captured_date)`; keeps the projected stat columns + `_horizon` (+ `_row_hash` per design open question); `captured_date DATE` is the as-of key; `feature_version` from the session var. Verify: `sqlfluff` (duckdb config) clean; a `feat.py`-driven test builds it from a seeded `raw.fangraphs_projection` + `core.player` and an ASOF query returns the latest `captured_date <= D`.
- [ ] 4.2 Append `("feat.fangraphs_projection", "duckdb/feat_fangraphs_projection.sql")` to `feat.py::_FEATURES` after `feat.game`. Verify: `mlb build` on a DB without `raw.fangraphs_projection` skips it cleanly (pre-check); with it, `feat.fangraphs_projection` lands and a second `mlb build` produces identical rows.
- [ ] 4.3 A PIT test: two snapshots for one key (`captured_date` D1 then D2, values moved); an as-of query at a date between D1 and D2 returns the D1 values, at/after D2 returns D2, and never a `captured_date > query` row.

## 5. `mlb doctor` checks

- [ ] 5.1 `report.health_check()` — row counts for the three relations; `core.team` join coverage for `gold.fangraphs_park_factors`; a check that `gold.fangraphs_guts` has a row for every `gold.batting_season` season `>= 2002`. `feat.py::health_check()` (or the feat doctor surface) — `core.player` join coverage for `feat.fangraphs_projection`. Verify: `test_health.py` / `test_doctor.py` — each new check present; a seeded gap (missing 2019 constant, unresolved team code) turns it red.

## 6. Rights guard

- [ ] 6.1 `tests/unit/` — assert no relation in `export.RELATIONS` / `serve.RELATIONS` whose `qualified_name` starts `gold.fangraphs_` has `profile == "public_safe"`; assert `require_sources("public_safe", ["fangraphs"], purpose="test")` raises `SourceProfileError` naming the source and `docs/SOURCE_RIGHTS.md`. Verify: the test passes now and would fail if a `public_safe` entry were added.

## 7. Docs

- [ ] 7.1 `docs/DATA_DICTIONARY.md` + `docs/TABLE_CONTRACTS.md` — the three relations, their grain, source, null policy, and the **`local_research` — never public_safe / published / baseline-model input; `gold.fangraphs_guts` is a reference/cross-check, publishable wOBA is computed from `core.play`** banner. `docs/RESEARCH.md` — note the fixed `research.py` weights can be replaced by a `gold.fangraphs_guts` join for internal era-accurate work (follow-up change). `docs/SOURCE_RIGHTS.md` — the derived relations inherit the FanGraphs row. `docs/DECISIONS.md` — new ADR (FanGraphs constants/park-factors → `gold` reference; projections → `feat.*`; all `local_research`). Verify: `grep` the new table/column names across `docs/` leaves nothing stale; `openspec validate fangraphs-conform --strict` passes.
- [ ] 7.2 Sync the delta into `openspec/specs/fangraphs-conform/spec.md` (new capability — created on archive). Verify: `openspec validate --all` after a dry archive.

## 8. Verification (owner-run against production)

- [ ] 8.1 `mlb migrate` + `mlb report` + `mlb build` on production `mlb`. Verify: `gold.fangraphs_guts` ~156 rows; `gold.fangraphs_park_factors` ~30/modern-season; `feat.fangraphs_projection` matches `raw.fangraphs_projection` row count (minus id-unresolvable); `mlb doctor` green; a hand wOBA recompute for one 2015 batter using `gold.fangraphs_guts` weights matches FanGraphs' published wOBA within 0.001.
- [ ] 8.2 Confirm no `gold.fangraphs_*` appears in a `mlb export --profile public_safe` bundle (should be impossible by the guard, verify anyway).
