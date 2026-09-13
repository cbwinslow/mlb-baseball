## 1. Dependency

- [x] 1.1 Add `fungo>=2.0,<3` to `[project.dependencies]` in `pyproject.toml`; run `uv lock` then `uv sync`; verify `python -c "import fungo.fangraphs; print(fungo.fangraphs.get_guts_constants()[:1])"` returns a real row inside the project venv. — done; live `get_guts_constants()` / `get_park_factors(2024)` / `get_leaders('bat',2024,2024,ind=1,qual=0)` all return real data in `.venv`.
- [x] 1.2 Confirm `curl_cffi` resolved as a transitive dependency and imports cleanly in CI's Python (`python -c "import curl_cffi"`); note the resolved version in `docs/DECISIONS.md` ADR. — `curl-cffi==0.16.3` resolved + imports clean; version to be recorded in ADR-288 (task 9.4).
- [x] 1.3 **(added during apply)** `fungo` requires Python >=3.12; raise the project floor: `requires-python = ">=3.12"`, four `python-version` pins in `.github/workflows/ci.yml`, `.github/workflows/pages.yml`, `.devcontainer/Dockerfile`, `ruff target-version = "py312"`, `ignore = ["UP046","UP047"]` (avoid a PEP 695 restyle of existing generics). Verify ruff + mypy + sqlfluff + `mkdocs --strict` + full unit suite + representative integration slice all pass on 3.12. — done: ruff clean, mypy 214 files, SQL lint ok, mkdocs strict ok, 1205 unit pass, 32/32 integration slice pass.

## 2. Connector skeleton

- [x] 2.1 Create `mlb_baseball/connectors/fangraphs.py` with `SOURCE = "fangraphs"`, module docstring covering the access seam and per-table strategy, and stubbed `bootstrap()`, `update()`, `health_check()`; verify `python -c "from mlb_baseball.connectors import fangraphs"` imports.
      → mlb_baseball/connectors/fangraphs.py created (full impl, not a stub); imports clean.
- [x] 2.2 Register `fangraphs` in `mlb_baseball/registry.py` `CONNECTORS`; verify `mlb ingest --help` lists `fangraphs` as a source choice and `python -c "from mlb_baseball.registry import CONNECTORS; assert 'fangraphs' in CONNECTORS"` passes.
      → Registered in registry.py CONNECTORS as 'fangraphs'; `mlb ingest --help` lists it; import assert passes.
- [x] 2.3 Add a thin `fungo`-call wrapper (`fungo` does its own transient retry internally — `net.call_with_retry` is `requests`-only and not used here, see design D6) that catches `fungo` `FangraphsError` / `RequestError`, logs verbatim, and re-raises (no extra retry); unit-test with a monkeypatched call that raises `FangraphsError` and assert it propagates and is logged once.
      → `_fg_call` catches FangraphsError/RequestError, logs verbatim, re-raises (fungo does its own transient retry; net.call_with_retry not used — design D6). test_fg_call_reraises_and_logs_fangraphs_error + test_fg_call_reraises_request_error.

## 3. Season leaderboards

- [x] 3.1 Implement `_load_leaderboard(conn, stat_group, season)` calling `get_leaders(stat_group, season, season, ind=1, qual=0)`, wrapping rows in a DataFrame, tagging `_season`, and calling `load_dataframe(..., scope_column="_season", scope_value=str(season))` for `raw.fangraphs_batting` / `_pitching` / `_fielding`; unit-test column tagging and scoped-replace call with a captured `fungo` fixture.
      → `_load_leaderboard` done; `ind=1, qual=0`; `_frame()` renames colliding sign-variant cols (-WPA/+WPA, K-BB%/K/BB+). tests/integration/test_fangraphs_load.py.
- [x] 3.2 Implement `bootstrap()`'s leaderboard loop over the discovered season range with a `season_already_loaded` skip for completed prior seasons and per-season try/except that logs and continues; integration-test against real PostgreSQL with a 2-season captured fixture that a mid-run failure on season 2 leaves season 1 committed.
      → `bootstrap()` loop + `season_already_loaded` skip + `_run_unit` isolation. test_bootstrap_skips_a_failing_unit_and_continues.
- [x] 3.3 Implement `update()` reloading only the current season for all three boards; integration-test idempotency — run `update()` twice, assert equal row counts and grain for the current season.
      → `update()` current season only. test_update_reloads_current_season_only + test_update_is_idempotent. Live smoke: fielding stayed 2236/2299/2246 per season across two updates.
- [x] 3.4 Record the observed earliest season that returns rows for each board (run against real FanGraphs once) and document it in the connector sidecar; verify early-season advanced columns land as SQL NULL, not 0.
      → Production bootstrap 2026-09-10 (~28 min): batting/pitching/fielding 1871-2026, prospects 2010-2026, splits 2002-2026, park factors 1901-2026 (basic) / 2002-2026 (handedness). Recorded in the sidecar 'Observed coverage' table. Advanced cols null (not 0) for early seasons.

## 4. Reference boards (guts, park factors, prospects)

- [x] 4.1 Implement `raw.fangraphs_guts` as a whole-table replace from `get_guts_constants()`; integration-test double-run idempotency and that historical rows are byte-stable across a re-run.
      → `_load_guts` whole-table replace. test_load_guts_whole_table_replace_is_idempotent. Live: 156 rows stable.
- [x] 4.2 Implement `raw.fangraphs_park_factors` and `raw.fangraphs_park_factors_handedness` as per-season scoped replaces from `get_park_factors(s)` / `get_park_factors_by_handedness(s)`; unit-test the per-season call/tag, integration-test scoped replace.
      → `_load_park_factors` both boards per-season. test_load_park_factors_loads_both_boards_per_season. Live: 30/season each.
- [x] 4.3 Implement `raw.fangraphs_prospects` as a per-season scoped replace from `get_prospect_board(s)`; integration-test one season loads and re-loads without duplication.
      → `_load_prospects` per-season scoped replace, schema_drift_policy='ignore' (THE BOARD columns vary by season). test_load_prospects_per_season_scoped_replace.
- [x] 4.4 Wire 4.1–4.3 into `bootstrap()` (full history) and `update()` (current season + guts reload); verify a full `bootstrap()` dry-run over a captured fixture populates every table.
      → Wired into bootstrap()/update(). Live smoke bootstrap populated every table.

## 5. Projection snapshot history

- [x] 5.1 Implement `_projection_rows()` iterating `PROJECTION_SYSTEMS` + `ROS_PROJECTION_SYSTEMS` × `{bat, pit}`, calling `get_projections(system, stats)`, tagging `_projection_system`, `_horizon` (`preseason`/`ros`), `_captured_date` (UTC date); unit-test horizon derivation and tagging from a captured fixture.
      → `_projection_rows` — 16 systems x {bat,pit}, tags _projection_system/_stat_group/_horizon/_captured_date/_row_hash, drops id-less rows. test_projection_rows_tags_horizon_and_skips_idless_rows + test_projections_tag_horizon_preseason_vs_ros.
- [x] 5.2 Implement change detection: read each `(_projection_system, stat_group, playerid)` key's most recent snapshot (`DISTINCT ON ... ORDER BY _captured_date DESC`), hash the projected-value columns, and append via `append_dataframe` only changed/new keys; unit-test with a fixture where 1 of 3 keys changed → exactly 1 row appended.
      → `_row_hash` md5 of value cols; `_latest_projection_hashes` DISTINCT ON key; `_changed_projection_rows` filters. test_changed_projection_rows_keeps_only_new_or_moved + test_projections_append_only_the_moved_key (1 of 2 keys moved -> 1 appended).
- [x] 5.3 Integration-test against real PostgreSQL: first `update()` seeds N rows; an immediate second `update()` with the same fixture appends 0; a third with one mutated projection appends exactly 1 and keeps the prior snapshot.
      → test_projections_seed_then_unchanged_rerun_appends_nothing + test_projections_append_only_the_moved_key. Live: 2nd _load_projections appended 0; 2nd full update kept projection at 9096.
- [x] 5.4 Wire projections into `update()` only (not the per-season `bootstrap()` loop); `bootstrap()` calls it once to seed the first snapshot. Verify `bootstrap()` on an empty DB creates `raw.fangraphs_projection` with today's snapshot.
      → projections in update() and one seed pass at end of bootstrap(). test_bootstrap_loads_multiple_seasons asserts raw.fangraphs_projection created.

## 6. Split leaderboards (curated)

- [x] 6.1 Define the curated split list (vs LHP, vs RHP, home, road, by month) as an explicit constant mapping to `fungo` `SPLIT_CODES` names/ints; unit-test each resolves via `fungo` without `ValidationError`.
      → CURATED_SPLITS (vs_lhp/vs_rhp/home/away + 6 month buckets). test_curated_splits_all_resolve_in_fungo + test_curated_splits_cover_the_spec_minimum.
- [x] 6.2 Implement `raw.fangraphs_split_batting` / `_split_pitching` as per-season, per-split scoped replaces (`_season` + `_split` in the delete key via `replace_dataframe_scopes` or a compound scope); integration-test one season × two splits load, re-load, and do not cross-delete each other.
      → compound `_scope`='{season}|{split}' replace key, `_season`/`_split` convenience cols. test_split_boards_scope_on_season_and_split_without_cross_delete. Live: home 1937 / vs_rhp 1967 side by side.
- [x] 6.3 Wire into `bootstrap()` / `update()`; verify the connector docstring and sidecar state that the full 292-code catalogue and per-player endpoints are deliberately out of scope (ADR-020/ADR-024 rationale).
      → Wired; docstring + sidecar + DATA_SOURCES state 292-code catalogue and per-player endpoints out of scope (ADR-020/ADR-024).

## 7. Depth charts — DEFERRED (struck during apply)

`get_depth_chart` needs a hand-verified 30-team URL-slug table
(`fungo.constants.TEAMS` has no slug; a wrong slug 500s) and returns a deeply
nested React-cache payload, not a leaderboard. Disproportionate for v1; MLB
Stats API already covers rosters/probables. Documented as an out-of-scope
follow-up in proposal.md, design.md, and the connector sidecar.

- [x] 7.1 Deferred — not built. Recorded as a follow-up non-goal.
- [x] 7.2 Deferred — not built.

## 8. Rights, health, cron

- [x] 8.1 Add the FanGraphs row to `docs/SOURCE_RIGHTS.md` (`local_research` only, fail-closed) with the terms/attribution/ML/review-date columns filled; verify `mlb ingest fangraphs --profile public_safe` exits with a `SourceProfileError` citing the doc and makes no network call (test with a network-blocking fixture).
      → docs/SOURCE_RIGHTS.md FanGraphs row added (local_research only, reviewed 2026-09-10). tests/unit/test_cli_dispatch.py: test_public_safe_profile_rejects_fangraphs (SystemExit 2, no bootstrap/update call) + test_source_profile_failure_names_fangraphs (names source + doc).
- [x] 8.2 Implement `health_check()` — `check_table_has_rows` for each core table + `check_last_run("fangraphs")` + a freshness threshold sized to the 6-hour cron; unit-test it reports failure when the last run is stale/failed and success on a fresh good run.
      → `health_check()` = 6 check_table_has_rows + check_last_run + check_recent_run(mode='update', DAILY_FRESHNESS_THRESHOLD_MINUTES). test_health_check_reports_tables_run_and_freshness. Live smoke: all 8 green.
- [x] 8.3 Add the `raw.fangraphs_*` tables to `mlb doctor`'s coverage/health surfaces where the other raw sources are listed; verify `mlb doctor` output includes a FanGraphs section.
      → doctor.py iterates CONNECTORS generically (line 237) -> registering `fangraphs` + its health_check() puts it in `mlb doctor`. Verified: fangraphs.health_check() returns 8 checks against real data. No doctor.py edit needed.
- [x] 8.4 Create `scripts/fangraphs_update.sh` (flock + timestamped log, mirroring `scripts/mlb_api_update.sh`) running `mlb ingest fangraphs --mode update`; test the flock path — a second invocation while a lock is held exits 0 without running.
      → scripts/fangraphs_update.sh (flock + log, MLB_FANGRAPHS_LOCK_FILE/LOG_FILE overridable, 6-hourly). tests/unit/test_fangraphs_update_script.py: runs `ingest fangraphs --mode update`; 2nd invocation while lock held logs 'already running, skipping' and does not call mlb again.

## 9. Docs / DOX

- [x] 9.1 Write `mlb_baseball/connectors/fangraphs.py.dox.md` per `connectors/AGENTS.md`'s sidecar contract (purpose, ownership, source contract, runtime contracts, data contracts, dependencies, downstream = none yet, known quirks incl. the okhttp exemption, verification, no child index).
      → mlb_baseball/connectors/fangraphs.py.dox.md written per connectors/AGENTS.md sidecar contract.
- [x] 9.2 Add the sidecar to `scripts/check_dox.py`'s enforced baseline; run `python scripts/check_dox.py` and verify it passes.
      → Added to scripts/check_dox.py REQUIRED_SIDECARS + connectors/AGENTS.md Reviewed Sidecar Coverage. `python scripts/check_dox.py` passes.
- [x] 9.3 Move FanGraphs from the Deferred section of `docs/DATA_SOURCES.md` into the main source table with its access method, coverage, and rights note.
      → docs/DATA_SOURCES.md: FanGraphs row added to the main Phase 1 table; Deferred entry now points at the fungo connector; bref row's 'unlike FanGraphs' note updated.
- [x] 9.4 Add ADR-288 to `docs/DECISIONS.md`: FanGraphs revived via `fungo` (okhttp exemption), `curl_cffi` accepted as a transitive dep, projections stored as de-duplicated dated snapshots, `local_research` rights.
      → ADR-288 added (newest-first) to docs/DECISIONS.md.
- [x] 9.5 Update `bref.py`'s docstring line that points at `docs/DATA_SOURCES.md`'s Deferred FanGraphs entry so it no longer says FanGraphs is simply unavailable (point at the new connector).
      → bref.py docstring updated — points at the fungo connector instead of calling FanGraphs simply unavailable.

## 10. Verification

- [x] 10.1 Run the full connector test module against real PostgreSQL (`pytest tests/ -k fangraphs`) and confirm all pass.
      → 14 unit (tests/unit/test_fangraphs_transform.py) + cli_dispatch profile tests + 15 integration (tests/integration/test_fangraphs_load.py) + 2 script tests all pass.
- [x] 10.2 Run `ruff` and `mypy` over `mlb_baseball/connectors/fangraphs.py` and the tests; confirm clean.
      → ruff check . clean; mypy 215 files clean; check_dox + sql-ownership lint clean.
- [x] 10.3 Run one real `mlb ingest fangraphs --mode bootstrap` under `local_research`, then `--mode update` twice; confirm row counts stabilise, projection snapshot dedupe works on the live second run, and `mlb doctor` shows `fangraphs` green. Record real row counts and per-board first seasons in the sidecar.
      → Full production bootstrap DONE 2026-09-10 against `mlb` (~28 min, ~715k rows): batting 108923 / pitching 52973 / fielding 180956 / guts 156 / park_factors 2752 / park_factors_handedness 750 / prospects 19153 / split_batting 167835 / split_pitching 134827 / projection 50511 (8 preseason + 8 RoS systems). Found + fixed a bug: handedness park-factor failures for pre-2002 rolled back the basic board for the same season (commit 8a2f555); backfilled 1901-2001 basic park factors. Column collision handled (wpa/wpa_pos/wpa_neg etc). health_check 8/8 green. Numbers in sidecar.
- [x] 10.4 Confirm `openspec validate add-fangraphs-connector --strict` passes and the diff touches no `core`/`gold`/model code.
      → openspec validate add-fangraphs-connector --strict passes. Diff touches connectors (fangraphs.py new, bref.py + registry.py + connectors/AGENTS.md), tests, scripts, docs/DATA_SOURCES + DECISIONS + SOURCE_RIGHTS, pyproject/CI/uv.lock — no core/gold/model/transforms/migrations code.
