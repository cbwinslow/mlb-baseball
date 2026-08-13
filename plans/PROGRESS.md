# Execution progress

This is an evidence log, not an authorization to merge or deploy. Update it at
each completed plan gate.

## Current state summary

- **Production state:** Production `mlb` is conformed through migration 0045.
  Verified baseline: 236,303 core games, 16,493,878 plays, and 13,400,779
  pitches; populated MLB keys are unique and core references have no orphans.
  Remaining provider-history pitch gaps retain their source keys and are not
  guessed. `gold.game_feature` is intentionally empty pending a separately
  reviewed feature rebuild.
- **Test database:** The current reusable local test database is `mlb_test`.
  Older evidence below may refer to `mlb_test_codex`, which is not present on
  the current host and must not be recreated without owner authorization.
- **Plan 01 status:** Core identity/conformance remediation is complete under
  prior owner authorization. The active test-only package is measured database
  readiness plus the first narrow point-in-time game-feature family.
- **Audit method:** Read-only static audit completed; no tests were run during the static audit, and no test pass is claimed.
- **Plan 02 status:** SQLMesh foundation/candidate gate accepted; overall plan incomplete and deferred behind 01F remediation.
- **Next package:** feature-family rehearsal, measured workload evidence, and
  production-safe recommendation; no production write is authorized.

### Experiment-lab rehearsal — 2026-08-12 (test database only)

- Migration 0047 adds content-addressed `game_base_v1` snapshots, declared
  experiments, and per-fold artifacts/results. Each snapshot preserves its
  source selection, schema, source watermark, environment/lock identity, code
  revision, keys, cutoffs, values, and resolved target rather than relying on
  the mutable `gold.game_feature` rebuild.
- The rehearsal runs home-rate, Log5, sequential Elo, regularized logistic
  regression, histogram gradient boosting, and XGBoost against one common
  chronological sample. Opening-game rate nulls stay retained-but-excluded for
  the Log5 common comparison; Python estimators use explicit median plus
  missing indicators.
- The default development plan tests 2016–2024 by calendar year, reserves 2025
  as untouched final holdout, and treats 2026 as forward monitor only. No
  production model write, promotion, hyperparameter search, or performance
  claim is authorized.

### First point-in-time feature rehearsal — 2026-08-12 (test database only)

- A read-only production sample (2008, 2015, 2024–26) was copied into
  `mlb_test`, conformed, and rebuilt through the strict `mlb features` path.
  It produced 4,181 canonical games, 3,920 plays, 14,716 pitches, and 2,468
  MLB-keyed regular-season feature rows. The database audit had 32 passes,
  zero warnings, and zero failures (four expected empty-table skips).
- The base feature contract is now explicit: `mlb_game_pk` is the one output
  identity; `feature_cutoff_at` is the retained MLB schedule first-pitch time;
  source schedule revisions remain raw history; only completed regular games
  before that ordered cutoff contribute to a row. Fixture coverage proves
  doubleheader ordering, schedule-history collapse, first-game nulls,
  scheduled labels, idempotency, and raw/core immutability.
- Measured representative lookup plans used the existing key/partition indexes:
  game lookup 0.016 ms, team history 0.284 ms, game-to-play 0.053 ms, and
  game-to-pitch 0.123 ms in the rehearsal. A production read-only
  player-season scan was 34.980 ms. No index was added: a separate production
  team-history plan identified a future candidate workload, but the bounded
  rehearsal did not demonstrate a material improvement sufficient to justify a
  new write cost.

### Team prior offense/defense — 2026-08-12 (test database only)

- `team_prior_offense_defense_v1` (`mlb_baseball/model/team_rate.py`, ADR-061)
  adds prior rolling team OBP/SLG/ISO/BB%/K% (admission queue OFF-01/02/03)
  and prior runs-for/allowed averages (OFF-08/DEF-01) as `gold.game_feature`
  enrichment columns. Migration `0050` adds 14 nullable columns.
- Hand-computed fixture tests passed for both the Retrosheet-based rate
  stats and the derived run-environment average; health checks added and
  wired into `mlb doctor` via `model.health_check()`.
- Not wired into `run()`/`build_feature_stage()` or `game_base_v1` — same
  dormant-until-wired status as every existing sibling enrichment family,
  consistent with Plan 01F's production-cutover block.

### Admission-queue contract closed for team_prior_offense_defense_v1 — 2026-08-13 (issue #8, ADR-062)

- A documented min-sample gate (`MIN_PA=10` for OBP/BB%/K%, `MIN_AB=8` for
  SLG/ISO) replaced the earlier `> 0` denominator guard in `team_rate.py`
  and `team_rate_retrosheet_update.sql` (`805ad2e`; real-value ISO test
  coverage added after review, `4be0908`) — new precedent, recorded as
  ADR-062.
- Migration `0051` adds `gold.game_feature.home_pa`/`away_pa`, populated
  unconditionally from the same `pa_sum` the gate uses, so a below-threshold
  row is distinguishable from one with no data at all (`aec00dc`).
- A new regression test proved `compute_run_environment()` already correctly
  excludes postponed observations and orders doubleheaders by game_number
  (`ee92003`) — no production code changed; the base feature family
  (migration 0046) already handled it.
- Historical-era coverage for OFF-01 was measured directly against
  production `mlb`: zero NULLs/empty values in `bat_event_fl`/`event_cd`/
  `ab_fl`/`sf_fl` across every decade 1900s–2020s (16,465,588 rows), no
  coverage gap (`b75c5fc`, `docs/RAW_CORE_GOLD_FIELD_CENSUS.md`).
- All five admission-queue rows (OFF-01/02/03/08, DEF-01) updated to final
  status in `docs/FEATURE_ADMISSION_QUEUE.md`. DEF-01's separate
  pitching-vs-defense documentation distinction was never part of issue #8's
  scope and remains open, noted explicitly in that row rather than claimed
  done. Issue #8 closed.

## Plan 00A/00B — 2026-08-05

### Workspace inventory

| Location | Commit / state | Scope | Decision |
|---|---|---|---|
| `main` | `8b0476f` plus uncommitted review, linkage, log5, evaluation, provenance, plans | Plan 00/01 work in progress | retain; independently verify before integration/commit |
| totals worktree | `e91f456` | `0029_gold_total_prediction.sql`, `total-v1`, tests | revise/defer until provenance and evaluation contracts exist |
| reporting worktree | `86013ee` | `0030_gold_reporting.sql`, reporting marts, tests | defer until source-profile/rights gate and serving contract review |
| stacking worktree | `e35d722` | `stack-v1`, tests | defer; must use cutoff-safe, strictly out-of-fold base predictions |
| SQLMesh spike | `20a2dc4` | SQLMesh experiment and tie-outs | defer as reference; reconcile its older base/dependency changes in Plan 02 |

### Evidence and decisions

- Totals and reporting migration numbers are no longer in conflict: totals owns
  `0029`, reporting owns `0030`. Neither is applied or merged.
- Totals cleanly separates continuous run prediction from win probability and has
  focused tests, but it currently lacks Plan 01 immutable model/artifact/run and
  prediction-cutoff provenance. It cannot be promoted before those contracts.
- Reporting directly uses Baseball-Reference-derived inputs. Its public-serving
  eligibility is unknown until Plan 01D enforces source profiles; it must not be
  exposed as a public mart beforehand.
- Stacking deduplicates snapshots and uses a chronological split, but its base
  predictions are not proven strictly out-of-fold and are not constrained to
  pre-first-pitch snapshots. It must remain an unsaved research negative result.
- The SQLMesh spike tied out three models but comes from an older base and alters
  dependency lockfiles. It is evidence for Plan 02, not a direct merge candidate.

### Authorization boundary

The active goal prohibits merging, committing, deleting worktrees, production
data writes, and infrastructure/security changes. Plan 00C is therefore pending
explicit owner authorization after Plan 01 verification.

## Plan 01A/01B/01C — 2026-08-05 (in progress)

### Verification evidence

- Dedicated `mlb_test_codex` has migrations through `0031_model_provenance.sql`.
- Focused unit, lint, and diff checks passed before integration verification.
- Isolated integration verification passed for the conformance linkage regression,
  log5-v2 prediction regression, game-grain evaluation, and model-registry
  registration after test-fixture repair (`4 passed` in the final affected subset).
- Default pytest collection exposed duplicate unit/integration provenance test
  module names; the unit file was renamed to `tests/unit/test_provenance.py`.
- A shared dynamic `raw.mlb_schedule` fixture is now additive in
  `test_model_log5.py`, so a table first created by another integration module
  gains the columns this fixture needs instead of relying on test order.

### Remaining Plan 01 work

- GBM runtime now writes content-addressed artifacts, registers an immutable
  candidate/champion identity, and links each prediction to `meta.model` and
  `meta.model_run`. The run record includes the best currently available
  in-place feature-table identity (`row count`, `_built_at`, latest game date)
  rather than pretending a feature snapshot table already exists. Focused
  provenance tests passed (`4 passed`); GBM integration process completed but
  this terminal wrapper suppressed pytest's final summary, so it remains due
  for the final sequential verification pass.
- Migration `0032_feature_snapshot_evaluation.sql` adds durable feature
  fingerprint and evaluation-result records without altering `0031` or the
  deferred worktree migrations. `feature_snapshot()` persists only the
  currently honest in-place identity (selection, row count, build timestamp,
  and latest game date); it explicitly does not claim to preserve old feature
  rows. Evaluation now creates a terminal `evaluate` run and one immutable
  metrics payload. Focused provenance/evaluation verification passed (`7
  passed`).
- Log5-v2 and Elo-v1 are now deterministic registered baselines. Their
  predictions are linked to model, run, data cutoff, and feature snapshot;
  focused integration verification passed (`6 passed`).
- GBM champion promotion now requires an absolute held-out log-loss gain of at
  least `0.002` over both baselines, with the threshold and observed gains
  persisted in `metrics_json`; a bare point-estimate win can no longer promote
  a model. Static checks passed. The terminal wrapper again suppressed the
  final output from the long GBM integration process, so no broad-pass claim is
  made from that invocation alone.
- Extend provenance to deterministic baseline/market models and add immutable
  feature snapshots plus persisted evaluation/calibration outputs before calling
  01C complete. Champion promotion also still needs a practical-improvement
  threshold, not only the current point-estimate comparison.
- Finish named-cutoff evaluation coverage and persistent/calibration outputs.
- `docs/SOURCE_RIGHTS.md` now records source evidence and a conservative
  three-profile policy. `mlb_baseball.source_profiles` is wired into `mlb
  ingest`, `mlb bootstrap`, and `mlb update`: `public_safe` is fail-closed and
  currently allows only Retrosheet connector families; `licensed_full` is no
  broader until an actual license is recorded; `local_research` remains the
  explicit default. Unit dispatch/profile verification passed (`20 passed`).
  Feature/training/serving/download/content lineage enforcement cannot be
  completed until the planned lineage-bearing feature and serve objects exist;
  public serving is therefore still prohibited.
- `docs/DBA_LEAST_PRIVILEGE_RUNBOOK.md` supplies a non-executed, reversible
  role/network/TLS/secret-permission checklist and proposed SQL. No roles,
  host rules, TLS settings, secrets, or production data were changed.

### Authorization gate reached

The active objective explicitly prohibits merging/committing worktree changes
and changing database roles/network security without owner approval. Plan 00C
therefore remains pending integration authorization. Plan 01E has a prepared
runbook but cannot execute the required role-capability tests until the owner
authorizes test-role creation (and separately any production role/network
change). Public serving remains prohibited until Plan 05 creates lineage-aware
`serve` objects; the current profile guard is ingress-only by design.

### Delegation note

Two bounded Antigravity `accept-edits`/`plan` calls timed out after five minutes
without returning a handoff. One left no requested source-profile change; a
separate timed-out test-fixture attempt left only its requested module rename and
formatting edits. Subsequent local inspection and isolated verification are the
controlling evidence.

### Authorized baseline integration — 2026-08-05

Owner authorization was received. Retained main-worktree changes were committed
as `d5597dc` (`Establish correctness, provenance, and source profile baseline`).
Deferred totals, reporting, stacking, and SQLMesh worktrees were not merged.
The retained files passed scoped Ruff format/check and 28 focused unit tests.

## Plan 02A — SQL ownership inventory (2026-08-06)

- Read-only SQL inventory completed and recorded in `docs/SQL_OWNERSHIP.md`.
- SQLMesh candidates are deterministic, set-based core/gold relations;
  connectors, identity reconciliation, sequential algorithms, and operational
  parameterized statements remain Python-owned. DDL remains in migrations.
- Confirmed duplicated wOBA/wRC+, FIP/out-count, and Pythagenpat definitions.
  The first migration target is the mutating `gold.game_feature` feature-family
  pipeline, beginning with the already-spiked venue/park-factor/team-wOBA
  models—not a wholesale `conform.py` rewrite.

## Plan 02B — SQLMesh foundation verification (2026-08-06)

- Installed the already-locked `sqlmesh==0.236.1` development dependency;
  no package constraints or lockfile entries changed.
- SQLMesh DuckDB tests passed (`2` tests). The pre-existing disposable
  `mlb_spike` gateway connected successfully; no new database was created.
- Reviewed `sqlmesh plan --no-prompts`: it ran the unit tests, showed the
  three managed model backfills, and aborted at the explicit apply prompt.
  The reviewed plan was then applied only to `mlb_spike`: `core.venue` 260
  rows, `gold.park_factor` 171 rows, `gold.team_woba` 19,436 rows.
- All eight declared SQLMesh audits passed (venue uniqueness/non-null;
  park-factor uniqueness/non-null/range; team-wOBA uniqueness/non-null/range).
  `mlb`, `mlb_test`, and `mlb_test_codex` were not touched by SQLMesh.
- `docs/SQLMESH_OPERATIONS.md` now records the current spike-only gateway,
  reproducible DuckDB/plan/audit commands, required candidate/test/prod
  environment separation, state/naming requirements, promotion gates, and
  bounded restatement/rollback procedure. It explicitly prohibits creating a
  new test database or targeting `mlb` without a separately approved config.
- SQLMesh external-model declarations now use catalog-neutral logical names,
  so a future explicitly configured `mlb_test_codex` candidate gateway can use
  the same project without a copied test database. DuckDB tests (`2 passed`)
  and the existing spike connection check passed; no plan/apply ran.

## Plan 02C — parity gate (2026-08-06)

- Reviewed `model.park.compute` against the SQLMesh spike. The Python contract
  is demand-driven by `gold.game_feature`, including seasons with upcoming
  games but no completed home game; the spike model is intentionally eager and
  cannot yet replace it exactly.
- The existing `mlb_spike` fixture has no `gold.game_feature`, so it cannot
  prove that production contract. No semantic SQLMesh change, new database, or
  fixture workaround was introduced. Promotion is deferred until a named
  game-feature-demand relation is available and full/sampled parity can be
  tested.
- `core.venue` is now a safer first conformance parity prerequisite: Python
  and its SQLMesh model both choose the lowest numeric MLB venue ID for a
  duplicate exact-normalized name, replacing the prior implicit PostgreSQL
  `UPDATE ... FROM` selection. The focused venue integration run used only the
  existing `mlb_test_codex`; SQLMesh DuckDB tests passed (`2 passed`). The
  Python writer remains in place pending an explicit environment/writer cutover.
- A draft named completed/scheduled game-demand model was intentionally not
  retained after its DuckDB fixture exposed an identity-contract issue: the
  spike's `core.venue` model has the natural park key but not the referenced
  PostgreSQL surrogate `core.venue.id`. `docs/SQL_OWNERSHIP.md` now makes
  identity preservation a hard promotion gate; no database was applied or
  changed by the draft.
- Park factor's production transformation SQL is now the named resource
  `mlb_baseball/sql/park_factor_update.sql`; `model.park` retains only its
  parameter/connection orchestration. Resource, park, and dependent wRC+
  coverage passed against existing `mlb_test_codex` (`8 passed`). A shared wRC+
  fixture now adds its required raw columns when another test created a narrower
  table first; no database was created.
- `core.venue`'s base insert and deterministic optional enrichment are now
  named `mlb_baseball/sql/conform_venue_*.sql` resources, while Python retains
  only optional-source/error and transaction orchestration. Named-resource and
  focused venue parity coverage passed against existing `mlb_test_codex` (`7
  passed`); no database was created.
- Prior-season team-speed's stable update is now the named resource
  `mlb_baseball/sql/team_speed_update.sql`; Python keeps only source existence
  detection and orchestration. Resource and feature coverage passed against
  existing `mlb_test_codex` (`9 passed`); no database was created.
- Prior-season OAA's stable update is now the named resource
  `mlb_baseball/sql/team_oaa_update.sql`; Python keeps only optional-source
  detection and orchestration. Resource and feature coverage passed against
  existing `mlb_test_codex` (`11 passed`); no database was created.
- Prior-season catcher framing's stable update is now the named resource
  `mlb_baseball/sql/team_framing_update.sql`; Python retains the source check
  and the small, reviewed team-map parameterization. Resource and feature
  coverage passed against existing `mlb_test_codex` (`11 passed`); no database
  was created.
- Prior-season team WAR's stable update is now the named resource
  `mlb_baseball/sql/team_war_update.sql`; Python retains only the reviewed
  current-era team-map parameterization and orchestration. Resource and feature
  coverage passed against existing `mlb_test_codex` (`11 passed`); no database
  was created.

## Plan 02D — atomic artifact landing (2026-08-06)

- `manifest.download()` now writes content to a same-directory temporary file
  and atomically replaces the destination only after the full response is
  written. Manifest JSON uses the same write-then-replace pattern.
- Focused Ruff check and manifest suite passed (`14 passed`). No database was
  created or changed.
- Manifest status transitions now optionally record parser version and a stable,
  order-sensitive source-schema fingerprint. The backwards-compatible manifest
  suite passed (`15 passed`).
- Retrosheet CSV loads now actually record parser version and a table-qualified
  source-schema fingerprint after every successful archive load. Manifest and
  connector coverage passed against existing `mlb_test_codex` (`19 passed`);
  no database was created.
- Retrosheet event archives now record their cwevent/cwgame parser version and
  deduplicated table-qualified output-schema fingerprint after successful loads.
  Its fixture now clears only its two disposable raw tables before/after each
  test, preventing unrelated stale-table drift warnings. Focused integration
  coverage passed against existing `mlb_test_codex` (`7 passed`); no database
  was created.
- `track_run()` now takes a per-source PostgreSQL advisory lock before recording
  an active run and always releases it on exit. Two independent connections to
  the existing `mlb_test_codex` database proved that an overlapping same-source
  run is rejected and that a subsequent run succeeds after release (`7 passed`);
  no database was created.
- The Retrosheet event and box-score parsers now unpack remote ZIP files only
  through a shared temporary-directory extractor. It rejects traversal paths,
  links/special files, excessive member count/size, and implausible compression
  ratios before writing any member. Focused archive, event-split, and Chadwick
  suites passed (`28 passed`); no database was used or created.
- Retrosheet roster-member copies now also validate each ZIP member before
  reading and write only its safe basename into the temporary parser directory.
  Archive and Chadwick suites passed (`28 passed`); no database was used or
  created.
- Shared network calls now retry only transient exceptions or statuses, respect
  a bounded numeric `Retry-After` response, and stop immediately for confirmed
  non-transient 4xx errors. Focused network and manifest suites passed (`27
  passed`); no database was used or created.
- Dynamic raw loading now rejects empty/sanitization-colliding column names and
  detects added/removed columns before mutation. Default loaders emit a visible
  drift warning; the stable Retrosheet CSV contract uses a blocking policy so a
  changed conformance input cannot be accepted without review. Loader and
  Retrosheet integration coverage passed against existing `mlb_test_codex` (`17
  passed`); no database was created.
- Append-only loads now require a declared, non-null observation identity and
  reject duplicate identities in a batch. Market snapshots use market/ticker
  plus capture time; live-game and probable-pitcher snapshots now persist an
  explicit `captured_at` with their source keys. Direct loader integration
  coverage passed against existing `mlb_test_codex` (`12 passed`); no database
  was created.
- The same two-connection advisory-lock test now proves the rejected connector
  connection remains usable after the active run releases the source lock
  (`7 passed` against existing `mlb_test_codex`); no database was created.

## Plan 02C continuation — deterministic verification and candidate gate (2026-08-06)

- Removed every test-time `CREATE DATABASE`/`DROP DATABASE` path. The
  unmigrated-database regressions now simulate PostgreSQL's real
  `UndefinedTable` error, and tests target only the existing
  `mlb_test_codex` database. Doctor's optional MLB API raw tables and
  conformance's complete dynamic raw-input inventory are reset on teardown,
  preventing stale optional sources from changing later test outcomes.
  Focused verification: `49 passed in 14.65s` for doctor/inventory/health;
  `2 passed in 13.87s` for conformance cleanup plus baseline run.
- Extracted `conform._build_teams`' stable set insert to
  `mlb_baseball/sql/conform_team_insert.sql`; its shared-max active-team
  sentinel behavior is covered through the existing real-Postgres regression
  (`1 passed in 13.20s`) and named-resource tests (`23 passed in 0.18s`).
- Added a non-default SQLMesh `candidate` gateway for only the existing
  `mlb_test_codex` database with `sqlmesh_plan02_candidate` state. The
  review-only `plan02_candidate` plan proposed only environment-suffixed
  candidate schemas and was declined before apply. The read-only
  `scripts/verify_sqlmesh_candidate.py` blocks promotion unless candidate
  venue surrogate IDs and completed/scheduled feature rows exactly match the
  existing Python-owned relations. Current models do not meet those contracts,
  so no writer was changed.
- The full repaired conformance suite was run alone against the existing test
  database: `TEST_DATABASE_URL=postgresql:///mlb_test_codex uv run pytest -q
  tests/integration/test_conform.py` → `46 passed in 643.44s (0:10:43)`.
  No test database was created and no concurrent pytest process was used.
- The read-only candidate parity checker now has an actual existing-database
  integration fixture (`1 passed in 0.91s`). It materialized only temporary
  `core__plan02_candidate` / `gold__plan02_candidate` relations, proved exact
  venue-ID, completed-game, and scheduled-game identities, then dropped those
  schemas. This validates the gate mechanics only; the current SQLMesh models
  remain ineligible to replace Python writers.
- Final Plan 02 acceptance audit passed: `uv run ruff check`; SQLMesh DuckDB
  tests (`2 passed`); safety/lock/doctor/inventory/health/candidate-gate tests
  (`57 passed in 15.73s`); named-resource tests (`23 passed in 0.12s`); and
  the isolated full conformance run (`46 passed in 644.44s (0:10:44)`). The
  review-only candidate plan proposed only suffixed schemas and was declined.
  Final database inspection found no candidate schemas or advisory locks.
  Plan 02 is accepted; Python writers remain active and SQLMesh cutover is a
  separate, owner-approved future milestone.

## Plan 02E — table contract baseline (2026-08-06)

- Added `docs/TABLE_CONTRACTS.md`, defining layer ownership plus grain, key,
  time/cutoff, lineage, and update behavior for raw product families and the
  core/gold/meta relations. It records that `gold.game_feature` is the
  completed-and-scheduled consumer-demand relation and that narrow gold
  families, not further sparse wide-table columns, are the intended path.
- `serve` remains deliberately deferred to Plan 05; no tables, schemas, or
  databases were created or altered for this documentation gate.

## Plan 02F — ClickHouse decision benchmark (2026-08-06)

- Read-only PostgreSQL `EXPLAIN ANALYZE` results on the original `mlb` are
  recorded in `docs/CLICKHOUSE_DECISION.md`: 13.4M-pitch three-season scan
  485 ms, rolling game primitive 36 ms, and prediction aggregate 25 ms.
  `gold.game_feature` has zero rows, so an experiment extract cannot honestly
  be benchmarked yet.
- A local ClickHouse binary exists but no server/replica is reachable. No
  ClickHouse database, replica, table, extension, or PostgreSQL object was
  created. Decision: retain PostgreSQL and revisit only after a stated SLO
  fails with reproducible concurrent benchmarks.

## Plan 01E — dedicated test role verification (2026-08-05)

- Added `tests/integration/test_least_privilege.py`. It creates a unique
  disposable NOLOGIN serving role and disposable serve schema in
  `mlb_test_codex`, then uses `SET ROLE` to prove allowed serve reads and denied
  raw/core/gold/meta reads and DDL, schema creation, and serve writes/drops.
- Focused verification passed: Ruff format/check and `1 passed in 0.41s`.
  Fixture teardown dropped the temporary schema and role. No production
  roles/network/TLS/credentials/data were changed.

## Plan 01F — Staged durable game-identity cutover static audit (2026-08-07)

- Read-only static audit of staged durable game-identity cutover completed.
- Status: Implementation exists but production cutover is BLOCKED pending remediation.
- Production `mlb` has not been touched and no production cutover is authorized.
- Tests were not run during this static audit; no test pass claimed.
- Remediation blockers:
  - Registry `meta.game_instance` is created in 0036 after 0035 fails, while backfill requires it.
  - Prediction `game_instance_key` lacks explicit NOT NULL cutover gate.
  - Interrupted `CREATE INDEX CONCURRENTLY` can leave invalid index and `IF NOT EXISTS` is not a safe retry.
  - Legacy prediction mapping through current feature rows is not historically unambiguous.
  - Deterministic batch ordering must use full old primary key.
  - `mlb doctor`, runbook, contracts, and public API need alignment and explicit read-only validation checks.
