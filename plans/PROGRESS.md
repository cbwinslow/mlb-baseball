# Execution progress

This is an evidence log, not an authorization to merge or deploy. Update it at
each completed plan gate.

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

## Plan 02D — atomic artifact landing (2026-08-06)

- `manifest.download()` now writes content to a same-directory temporary file
  and atomically replaces the destination only after the full response is
  written. Manifest JSON uses the same write-then-replace pattern.
- Focused Ruff check and manifest suite passed (`14 passed`). No database was
  created or changed.
- Manifest status transitions now optionally record parser version and a stable,
  order-sensitive source-schema fingerprint. The backwards-compatible manifest
  suite passed (`15 passed`).
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
