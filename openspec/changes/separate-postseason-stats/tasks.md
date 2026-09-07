## 1. Pipeline audit (do first — records the blast radius)

- [ ] 1.1 Walk every `gold` builder (`mlb_baseball/sql/*.sql`, `mlb_baseball/report.py`), every SQLMesh model in `transforms/models/`, every materialised view (`SELECT ... FROM pg_class WHERE relkind IN ('v','m')` whose def references game-level data), and every Python aggregation in `mlb_baseball/model/*.py` + `mlb_baseball/*.py`. Record in `openspec/changes/separate-postseason-stats/game-type-audit.md`: per relation — which `game_type`s it includes, where the filter is (file:line) or that it is missing, and the fix. Verify: the audit file lists every game-aggregating relation with a PASS (explicit filter) or GAP (fix noted).
- [ ] 1.2 For each GAP found in 1.1, add the explicit `game_type` filter. Verify: re-run the affected builder against a test DB; row counts change only where a postseason game was wrongly included; a targeted integration test covers each fix.

## 2. Fix the raw Baseball-Reference ingest

- [ ] 2.1 In `mlb_baseball/connectors/bref.py`, replace the `pybaseball.batting_stats_bref` / `pitching_stats_bref` calls with `pybaseball.batting_stats_range` / `pitching_stats_range` over `f"{season}-03-15"` → a regular-season end date (default `f"{season}-10-01"`, with a per-season override map for known late finishes / one-game playoffs — design.md D1). Verify: a unit test with pybaseball mocked asserts the date range passed excludes November; `basedpyright` / `ruff` clean.
- [ ] 2.2 Re-ingest `raw.bref_batting` / `raw.bref_pitching` for 2008–2026 after clearing the affected pybaseball `df_cache` entries (owner-run; document the exact commands). Verify: Marcus Semien 2023 in `raw.bref_batting` shows 162 G / 753 PA; a spot check of 3 more deep-playoff-team players across 2021–2025 shows regular-season game counts.

## 3. Rebuild `gold.player_season` / `gold.team_season` clean

- [ ] 3.1 Run `mlb report` against the re-ingested raw. Verify: `SELECT max(games) FROM gold.player_season` ≤ 162; the `verify_baseball_reference_tie_out.py` bulk cross-check (currently capped at 2019) passes with its ceiling raised to 2025 for a spot run.

## 4. New postseason relations

- [ ] 4.1 Migration(s) creating `gold.batting_postseason` / `gold.pitching_postseason` — same column shape as `gold.batting_season` / `gold.pitching_season` plus a `round` column (`wildcard` / `divisionseries` / `lcs` / `worldseries` / …) and the `is_combined` all-rounds row pattern; player-season and team-season grains. Verify: `mlb migrate` applies cleanly; the tables exist with the documented columns.
- [ ] 4.2 `mlb_baseball/sql/batting_postseason_build.sql` / `pitching_postseason_build.sql` + wiring into `mlb report` — the `*_game_build.sql` logic with the `game_type` filter set to the postseason types and a `round` dimension, rolled up to season + team + combined. Verify: an integration test seeds a known postseason (e.g. a small fixture) and asserts per-round and combined rows; idempotent rebuild.
- [ ] 4.3 Tie-out check: pick one well-documented modern postseason run (e.g. a World Series MVP) and assert `gold.batting_postseason` (or pitching) matches that player's Baseball-Reference postseason line. Verify: a case in `scripts/verify_baseball_reference_tie_out.py` or a dedicated check passes.

## 5. Guards

- [ ] 5.1 Add the two `mlb doctor` checks (design.md D4): the `gold.player_season` / `gold.team_season` regular-season envelope, and postseason-relation game-type purity. Verify: each check fails on a deliberately-corrupted fixture row and passes on the real rebuilt data.

## 6. Reconciliation + export + docs

- [ ] 6.1 Tighten the postseason-absorbing reconciliation tolerance in `mlb_baseball/model/starter.py` and `mlb_baseball/model/bullpen.py` now that `raw.bref_*` is clean; update their docstrings (the Blake Snell / postseason-mix note becomes "fixed in separate-postseason-stats"). Verify: the reconciliation `mlb doctor` checks pass at the tighter tolerance against rebuilt data.
- [ ] 6.2 `mlb_baseball/export.py` — allow-list entries for `gold.batting_postseason` / `gold.pitching_postseason` (`local_research`, same rationale as the season tables). Verify: `mlb export` lists them; the export test covers them.
- [ ] 6.3 Docs: update `docs/DECISIONS.md` (ADR-282 → resolved, name this change), `docs/RESEARCH.md` (the `raw.bref_pitching` season-aggregate note), `docs/DATA_DICTIONARY.md` + `docs/TABLE_CONTRACTS.md` (regular-season-only statement on `gold.player_season` / `gold.team_season`; new postseason relations documented), and `openspec/project.md`'s NOW block. Verify: `openspec validate --all` passes; links resolve.

## 7. Verification

- [ ] 7.1 Fresh-checkout smoke: a throwaway scratch DB, `mlb migrate`, seed, `mlb report`, confirm no postseason game lands in any regular-season relation and the postseason relations are populated only by postseason games. Verify: a script or documented manual run.
- [ ] 7.2 `openspec validate --all` and `openspec validate separate-postseason-stats --strict` exit 0. Full targeted test suite for the touched modules (`tests/integration/test_report*.py`, `tests/unit/test_bref*` / connector tests, doctor tests) passes. Verify: paste the test summary into the PR.
