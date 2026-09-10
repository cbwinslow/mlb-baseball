## 1. Dependency

- [ ] 1.1 Add `fungo>=2.0,<3` to `[project.dependencies]` in `pyproject.toml`; run `uv lock` then `uv sync`; verify `python -c "import fungo.fangraphs; print(fungo.fangraphs.get_guts_constants()[:1])"` returns a real row inside the project venv.
- [ ] 1.2 Confirm `curl_cffi` resolved as a transitive dependency and imports cleanly in CI's Python (`python -c "import curl_cffi"`); note the resolved version in `docs/DECISIONS.md` ADR.

## 2. Connector skeleton

- [ ] 2.1 Create `mlb_baseball/connectors/fangraphs.py` with `SOURCE = "fangraphs"`, module docstring covering the access seam and per-table strategy, and stubbed `bootstrap()`, `update()`, `health_check()`; verify `python -c "from mlb_baseball.connectors import fangraphs"` imports.
- [ ] 2.2 Register `fangraphs` in `mlb_baseball/registry.py` `CONNECTORS`; verify `mlb ingest --help` lists `fangraphs` as a source choice and `python -c "from mlb_baseball.registry import CONNECTORS; assert 'fangraphs' in CONNECTORS"` passes.
- [ ] 2.3 Add a `fungo`-call wrapper that routes through `mlb_baseball.net.call_with_retry` and re-raises `fungo` `FangraphsError` after logging it verbatim (no unbounded retry); unit-test the wrapper with a monkeypatched call that raises `FangraphsError` and assert it propagates and is logged once.

## 3. Season leaderboards

- [ ] 3.1 Implement `_load_leaderboard(conn, stat_group, season)` calling `get_leaders(stat_group, season, season, ind=1, qual=0)`, wrapping rows in a DataFrame, tagging `_season`, and calling `load_dataframe(..., scope_column="_season", scope_value=str(season))` for `raw.fangraphs_batting` / `_pitching` / `_fielding`; unit-test column tagging and scoped-replace call with a captured `fungo` fixture.
- [ ] 3.2 Implement `bootstrap()`'s leaderboard loop over the discovered season range with a `season_already_loaded` skip for completed prior seasons and per-season try/except that logs and continues; integration-test against real PostgreSQL with a 2-season captured fixture that a mid-run failure on season 2 leaves season 1 committed.
- [ ] 3.3 Implement `update()` reloading only the current season for all three boards; integration-test idempotency — run `update()` twice, assert equal row counts and grain for the current season.
- [ ] 3.4 Record the observed earliest season that returns rows for each board (run against real FanGraphs once) and document it in the connector sidecar; verify early-season advanced columns land as SQL NULL, not 0.

## 4. Reference boards (guts, park factors, prospects)

- [ ] 4.1 Implement `raw.fangraphs_guts` as a whole-table replace from `get_guts_constants()`; integration-test double-run idempotency and that historical rows are byte-stable across a re-run.
- [ ] 4.2 Implement `raw.fangraphs_park_factors` and `raw.fangraphs_park_factors_handedness` as per-season scoped replaces from `get_park_factors(s)` / `get_park_factors_by_handedness(s)`; unit-test the per-season call/tag, integration-test scoped replace.
- [ ] 4.3 Implement `raw.fangraphs_prospects` as a per-season scoped replace from `get_prospect_board(s)`; integration-test one season loads and re-loads without duplication.
- [ ] 4.4 Wire 4.1–4.3 into `bootstrap()` (full history) and `update()` (current season + guts reload); verify a full `bootstrap()` dry-run over a captured fixture populates every table.

## 5. Projection snapshot history

- [ ] 5.1 Implement `_projection_rows()` iterating `PROJECTION_SYSTEMS` + `ROS_PROJECTION_SYSTEMS` × `{bat, pit}`, calling `get_projections(system, stats)`, tagging `_projection_system`, `_horizon` (`preseason`/`ros`), `_captured_date` (UTC date); unit-test horizon derivation and tagging from a captured fixture.
- [ ] 5.2 Implement change detection: read each `(_projection_system, stat_group, playerid)` key's most recent snapshot (`DISTINCT ON ... ORDER BY _captured_date DESC`), hash the projected-value columns, and append via `append_dataframe` only changed/new keys; unit-test with a fixture where 1 of 3 keys changed → exactly 1 row appended.
- [ ] 5.3 Integration-test against real PostgreSQL: first `update()` seeds N rows; an immediate second `update()` with the same fixture appends 0; a third with one mutated projection appends exactly 1 and keeps the prior snapshot.
- [ ] 5.4 Wire projections into `update()` only (not the per-season `bootstrap()` loop); `bootstrap()` calls it once to seed the first snapshot. Verify `bootstrap()` on an empty DB creates `raw.fangraphs_projection` with today's snapshot.

## 6. Split leaderboards (curated)

- [ ] 6.1 Define the curated split list (vs LHP, vs RHP, home, road, by month) as an explicit constant mapping to `fungo` `SPLIT_CODES` names/ints; unit-test each resolves via `fungo` without `ValidationError`.
- [ ] 6.2 Implement `raw.fangraphs_split_batting` / `_split_pitching` as per-season, per-split scoped replaces (`_season` + `_split` in the delete key via `replace_dataframe_scopes` or a compound scope); integration-test one season × two splits load, re-load, and do not cross-delete each other.
- [ ] 6.3 Wire into `bootstrap()` / `update()`; verify the connector docstring and sidecar state that the full 292-code catalogue and per-player endpoints are deliberately out of scope (ADR-020/ADR-024 rationale).

## 7. Depth charts (separable — droppable without affecting 3–6)

- [ ] 7.1 Implement `raw.fangraphs_depth_chart` from `get_depth_chart(page)` over the ~30 team pages, appended as a `_captured_date` snapshot with the same change-detection dedupe as projections; integration-test one team page loads and a same-data re-run appends nothing.
- [ ] 7.2 Wrap 7.1 so a `FangraphsError` / parse failure on depth charts (the React-cache scrape, most fragile endpoint) logs and skips without failing the rest of `update()`; unit-test the skip path.

## 8. Rights, health, cron

- [ ] 8.1 Add the FanGraphs row to `docs/SOURCE_RIGHTS.md` (`local_research` only, fail-closed) with the terms/attribution/ML/review-date columns filled; verify `mlb ingest fangraphs --profile public_safe` exits with a `SourceProfileError` citing the doc and makes no network call (test with a network-blocking fixture).
- [ ] 8.2 Implement `health_check()` — `check_table_has_rows` for each core table + `check_last_run("fangraphs")` + a freshness threshold sized to the 6-hour cron; unit-test it reports failure when the last run is stale/failed and success on a fresh good run.
- [ ] 8.3 Add the `raw.fangraphs_*` tables to `mlb doctor`'s coverage/health surfaces where the other raw sources are listed; verify `mlb doctor` output includes a FanGraphs section.
- [ ] 8.4 Create `scripts/fangraphs_update.sh` (flock + timestamped log, mirroring `scripts/mlb_api_update.sh`) running `mlb ingest fangraphs --mode update`; test the flock path — a second invocation while a lock is held exits 0 without running.

## 9. Docs / DOX

- [ ] 9.1 Write `mlb_baseball/connectors/fangraphs.py.dox.md` per `connectors/AGENTS.md`'s sidecar contract (purpose, ownership, source contract, runtime contracts, data contracts, dependencies, downstream = none yet, known quirks incl. the okhttp exemption, verification, no child index).
- [ ] 9.2 Add the sidecar to `scripts/check_dox.py`'s enforced baseline; run `python scripts/check_dox.py` and verify it passes.
- [ ] 9.3 Move FanGraphs from the Deferred section of `docs/DATA_SOURCES.md` into the main source table with its access method, coverage, and rights note.
- [ ] 9.4 Add ADR-288 to `docs/DECISIONS.md`: FanGraphs revived via `fungo` (okhttp exemption), `curl_cffi` accepted as a transitive dep, projections stored as de-duplicated dated snapshots, `local_research` rights.
- [ ] 9.5 Update `bref.py`'s docstring line that points at `docs/DATA_SOURCES.md`'s Deferred FanGraphs entry so it no longer says FanGraphs is simply unavailable (point at the new connector).

## 10. Verification

- [ ] 10.1 Run the full connector test module against real PostgreSQL (`pytest tests/ -k fangraphs`) and confirm all pass.
- [ ] 10.2 Run `ruff` and `mypy` over `mlb_baseball/connectors/fangraphs.py` and the tests; confirm clean.
- [ ] 10.3 Run one real `mlb ingest fangraphs --mode bootstrap` under `local_research`, then `--mode update` twice; confirm row counts stabilise, projection snapshot dedupe works on the live second run, and `mlb doctor` shows `fangraphs` green. Record real row counts and per-board first seasons in the sidecar.
- [ ] 10.4 Confirm `openspec validate add-fangraphs-connector --strict` passes and the diff touches no `core`/`gold`/model code.
