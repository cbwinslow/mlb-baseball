## 0. Definitions and metric catalog (first)

- [ ] 0.1 Write the vocabulary (metric / stat / feature, decision 11) into the owning doc (candidate: `docs/DATA_DICTIONARY.md` or a short glossary linked from `docs/AGENTS.md`). Verify: one owner per term; `TABLE_CONTRACTS.md` and `FEATURE_STORE.md` link to it instead of redefining.
- [ ] 0.2 Inventory every existing metric/stat/feature (`docs/FEATURE_REGISTRY.md`, `metric-catalog`, gold tables, `feat.*`, `mlb_baseball/model/`) with keep / merge / retire / rework. Verify: one row each, with reason; owner signs off on the retire list.
- [ ] 0.3 Draw the gold-versus-`feat.*` line and list overlaps (`gold.game_feature*` vs `feat.game`). Verify: each overlap has a retirement or ownership decision.
- [ ] 0.4 Extend the target-metric list from research (papers, books, FanGraphs/Tango/Statcast, baseball.computer parity). Verify: each new metric has citation, grain, inputs, PIT rule, null policy.
- [ ] 0.5 For each kept/new metric, trace inputs to raw/core fields and mark missing ones. Verify: the list of core additions comes only from this trace.

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
