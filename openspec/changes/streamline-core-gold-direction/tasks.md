## 0. Definitions and metric catalog (first)

- [ ] 0.1 Write the vocabulary (metric / stat / feature, decision 11) into the owning doc (candidate: `docs/DATA_DICTIONARY.md` or a short glossary linked from `docs/AGENTS.md`). Verify: one owner per term; `TABLE_CONTRACTS.md` and `FEATURE_STORE.md` link to it instead of redefining.
- [ ] 0.2 Inventory every existing metric/stat/feature (`docs/FEATURE_REGISTRY.md`, `metric-catalog`, gold tables, `feat.*`, `mlb_baseball/model/`) with keep / merge / retire / rework. Verify: one row each, with reason; owner signs off on the retire list.
- [ ] 0.3 Draw the gold-versus-`feat.*` line and list overlaps (`gold.game_feature*` vs `feat.game`). Verify: each overlap has a retirement or ownership decision.
- [ ] 0.4 Extend the target-metric list from research (papers, books, FanGraphs/Tango/Statcast, baseball.computer parity). Verify: each new metric has citation, grain, inputs, PIT rule, null policy.
- [ ] 0.5 For each kept/new metric, trace inputs to raw/core fields (`metrics-trace.md`). Verify: every traced field is in `core-coverage.md`. This no longer limits what `core` carries (decision 10).

## 1. Audit what we have (read-only)

- [ ] 1.1 Run `mlb field-census --exact` against `mlb_test` and save JSON/markdown under `artifacts/census/`. Verify: both files exist and the summary lists counts per classification.
- [ ] 1.2 Cross-check with `information_schema.columns` (raw/core/gold/meta). Verify: a short note lists every raw field classed `unconformed_candidate` or `needs_research`, and nothing else is called a gap.
- [ ] 1.2a Note: `mlb_test` is schema-only (0 rows). The estimate census ran on production on 2026-10-08 (18 s, `artifacts/census/mlb_prod_estimate.*`; 3,738 needs_research, 1,328 raw_only, 8 canonical_core, 3 existing_gold, 0 unconformed) but its classifier is a typed list, so those counts are provisional. Verify: this note stays until 1.2c replaces the classifier.
- [ ] 1.2b Propose a read-only profile view over raw/core/gold/meta joining `information_schema.columns`, `pg_stats` and `pg_class` (type, null share, distinct count, size), plus view dependencies from `pg_depend`. Needs a numbered migration and owner approval before it touches production. Verify: one row per column after `ANALYZE`; row count matches `information_schema.columns`.
- [ ] 1.2c Spike column lineage with SQLMesh/sqlglot over `mlb_baseball/sql/*.sql` and `transforms/`. Verify: for ten known raw-to-core fields the lineage matches `conform` by hand; unresolved fields report "unknown"; list how much Python-moved data has no SQL lineage.
- [ ] 1.2d Rebuild the census as a query over 1.2b + 1.2c, with `pg_stat_statements` as a cross-check only. Verify: re-run reports a gap list that no longer depends on `_MAPPINGS`; counts differ from the 2026-10-08 run are explained.
- [ ] 1.3 Compare docs to the live database (`docs/TABLE_CONTRACTS.md`, `DATA_DICTIONARY.md`, `FEATURE_STORE.md`, `RAW_INVENTORY.md`). Verify: a list of doc/DB mismatches, each with its owning file.
- [ ] 1.4 Check `gold.game_feature` and `feat.game` for point-in-time safety (no post-game inputs). Verify: written result per feature group, per `mlb_baseball/model/AGENTS.md`.

## 2. baseball.computer parity and research backlog

- [ ] 2.1 Build the parity matrix (their staging/intermediate/metrics models vs our tables/views/metrics) from the GitHub model tree, no SQL copied. Verify: matrix file lists each of their models as have / partial / missing / out-of-scope.
- [ ] 2.2 Expand `docs/research/SABERMETRIC_LITERATURE_INDEX.md` into a ranked feature backlog (citation, grain, inputs, PIT rule, null policy, rights). Verify: every row has all columns; no uncited feature.
- [ ] 2.3 Record which backlog items already exist in `docs/FEATURE_REGISTRY.md` / `meta.metric`. Verify: no duplicate entries.

## 3. Decide tools with evidence

- [ ] 3.1 Time one representative gold query on Postgres vs DuckDB. Verify: timings and query text recorded in `design.md`.
- [ ] 3.2 SQLMesh spike: build one `feat.*` relation via SQLMesh on DuckDB reading `core`; compare with the existing builder. Verify: row-count and value parity report.
- [ ] 3.3 Write the ADR(s) for decisions 3 and 4 in `docs/DECISIONS.md` (next number, newest first) and update `design.md` statuses. Verify: ADR linked from design.md.
- [ ] 3.4 Decide MLflow timing and record it. Verify: one line in the ADR.

## 4. Cleanup (each step needs owner approval first)

- [ ] 4.1 For `baseball`, `letta`, `letta_user`: check grants and ownership in every database. Verify: written result per role. Keep `cbwinslow`, `mlb`, `postgres_exporter`.
- [ ] 4.2 With approval, drop the unused roles. Verify: `pg_roles` no longer lists them; dated entry in `changelog/`.
- [ ] 4.3 With approval, remove leftover `mlb_test_*_tmpl` databases using the project's reaper. Verify: database list shows only live ones; changelog entry.
- [ ] 4.4 Fix or archive stale docs found in 1.3 and update the nearest DOX files. Verify: `docs/AGENTS.md` index and links still resolve.
- [ ] 4.5 Update `openspec/project.md` NOW/NEXT/LATER with the agreed order. Verify: `openspec validate --all` passes.

## 5. Conform decomposition, audit and validation

- [ ] 5.1 Write the conform decomposition design (which steps become named `.sql`, `IMMUTABLE` functions, SQLMesh, or stay Python) and count the remaining inline SQL strings (268 in 75 files on 2026-10-08). Verify: every `conform.py` function has a destination.
- [ ] 5.2 Extract set-based `conform` builds one table at a time. Verify: each has a run-twice test proving the second run changes nothing, and parity against the old writer.
- [ ] 5.3 Tighten `scripts/lint_sql_ownership.py` (cover f-strings/variables; remove the `conform.py` exemption as tables move). Verify: lint passes and flags a planted violation.
- [ ] 5.4 Design the process audit log: per-step `meta` run records, `track=all`, `track_functions=pl`; review `conform._timed`. Verify: one `conform` run yields per-step time, rows and outcome, with pg_stat_statements cross-checked.
- [ ] 5.5 Write the validation ladder doc and source-by-grain tie-out matrix (roll-up play/pitch to game/season vs Lahman, Baseball-Reference). Verify: every core build lists its tie-out source; missing ones become tasks.

## 6. Core coverage (decision 10, ADR-305)

- [ ] 6.1 Confirm `core-coverage.md` with the owner (group priorities, grain per group). Verify: owner sign-off recorded in the file.
- [ ] 6.2 Widen `core.pitch` to all 122 `statcast_pitch` columns and `core.play` to the full Retrosheet/MLB play fields, one table at a time. Verify: run-twice test; row and value parity with `raw`; no column dropped without a written reason.
- [ ] 6.3 Add the new core tables in priority order from `core-coverage.md` (game context, box scores/lineups, umpires, transactions, parks, season stats, tracking, forecasts, awards). Verify: each has grain, key, PIT stamp, tie-out source and a `doctor` check.
- [ ] 6.4 Add `core` team-season league/division history (league, division, conference per season) from `mlb_team_history`, `lahman_teams`, `retrosheet_team`, cross-checked against `mlb_sport/league/division/conference` (these hold 20/15/6/2 rows; the earlier "empty" reading was a stale row estimate). Verify: every team-season has one league and division.
- [ ] 6.5 Add point-in-time market prices in `core` using `polymarket_price` and `kalshi_candle` (own change; strict-before-start rule; PIT tests).
- [ ] 6.6 Build `gold` normalizers: league-by-year averages, replacement levels, park/era adjustments. Verify: each cites its formula.
- [ ] 6.7 Assign the unassigned raw tables in `core-coverage.md` (review additions) to a grain and priority. Verify: all 150 raw tables appear in the file or have a written exclusion.
- [ ] 6.8 Add an era/rule-change reference table and a measurement-system field on pitch rows. Verify: each rule change has a dated source citation.
- [ ] 6.9 Researcher surface: generated data dictionary, versioned release snapshots, read-only role, rights-filtered export. Verify: a researcher can reproduce one published number from a snapshot.
- [ ] 6.10 Owner approved 2026-10-10, conditional on reliability: add a weather source and sportsbook closing lines. Research candidates (coverage, history depth, uptime, terms of use, cost), pick on evidence, then build each as a normal idempotent ingestion (run-twice test, bootstrap, `doctor` check). Verify: a written reliability comparison per source and a tie-out against Retrosheet weather / Kalshi-Polymarket results; no paid source without a further owner OK.

## 7. Nightly cost and incremental builds (from the 2026-10-10 external audit; claims unverified until measured)

- [ ] 7.1 Measure first: time every nightly step (conform, report, features/enrich, predict) with rows written and WAL bytes per step, plus the cause of each past failed run (`meta.ingestion_run`, logs). Verify: a table of step, seconds, rows, WAL; the 2026-10-09 failure is attributed to a cause with evidence (the handoff says network drop).
- [ ] 7.2 Incremental feature build: stop `features.build()` truncating all 219,925 `gold.game_feature` rows nightly; rebuild only unfinished or current-season games. Verify: second run changes nothing; values for closed seasons identical to the full rebuild; a PIT/leakage check passes.
- [ ] 7.3 Replace the ~41 sequential `UPDATE gold.game_feature` passes (`enrich_feature_stage`) with one insert or per-family tables joined by key (SQLMesh candidate, see task 3.2). Verify: row and value parity with the old path; WAL per run measured before and after.
- [ ] 7.4 Incremental `conform` for current-season rows, aligned with `openspec/changes/stable-ids-incremental-conform`. Verify: no duplicate work with that change; run-twice test.
- [ ] 7.5 Test Timescale compression on a copy of `raw.kalshi_candle` (neither big raw table is a hypertable today). Verify: measured size and query-time change on the copy; production only with owner approval.
