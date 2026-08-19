# Execution progress

This is an evidence log, not an authorization to merge or deploy. Update it at
each completed plan gate.

## Current state summary

- **Production state (superseded 2026-08-18, see "Plan 01F production
  cutover executed" below for the current state):** Production `mlb` was at
  migration 0052 as of 2026-08-13/14 evidence below; now at migration 0056
  with the `game_pk` uniqueness cutover applied and `core`/`gold` rebuilt.
  `gold.game_feature` had 217,340 rows and every enrichment module had run
  against it for the first time ever (2026-08-13/14, owner-authorized,
  one module at a time, health-checked after each): `park`, `team_rate`,
  `offense` (+`_live`), `starter` (+`_live`+`_probable`), `bullpen`
  (+`_live`+`_upcoming`), `oaa`, `speed`, `framing`, `war`. Every health
  check passed, including `starter`'s full 13,613-pitcher-season
  reconciliation against `raw.bref_pitching` (1.7% mismatch, within its
  documented 2.0% accepted rate) and `bullpen`'s 406,516-row outs
  reconciliation. Two bounds were widened for verified real small-sample
  cases (`41fe788`) and one stale docstring citation was synced with
  `docs/RESEARCH.md`'s prior correction (`7b4c4e2`).
- **Test database:** The current reusable local test database is `mlb_test`.
  Older evidence below may refer to `mlb_test_codex`, which is not present on
  the current host and must not be recreated without owner authorization.
- **Plan 01 status:** Core identity/conformance remediation is complete under
  prior owner authorization. The active test-only package is measured database
  readiness plus the first narrow point-in-time game-feature family.
- **Audit method:** Read-only static audit completed; no tests were run during the static audit, and no test pass is claimed.
- **Plan 02 status:** SQLMesh foundation/candidate gate accepted; overall plan incomplete and deferred behind 01F remediation.
- **Next package:** Remaining open GitHub issues (#9 items 3/4, #10 SQL lint script, #15 Astro progress site, #28/#29 narrow edge cases found during PR #25 review). #6 (mojibake names) and #7 (test pollution) are closed; #9 items 1/2/6 are fixed (items 3/4 remain open).

### Starter workload live and probable paths (pitcher_workload_v1_live, completed) — 2026-08-15

Completed extension of `mlb_baseball/model/starter_workload.py` (PIT-03) adding `compute_live()` and `compute_probable()` (ADR-069):

- **Live 2026 completed game path (`compute_live()`)**: Implemented via `mlb_baseball/sql/starter_workload_live_update.sql`, reusing `starter.py`'s `first_pitcher` CTE and `play_outs` LAG-diff running outs logic to compute rest days and trailing 7-day workload outs from `raw.mlb_playbyplay` for completed 2026 games. Gated on `f.home_starter_rest_days IS NULL` to ensure Retrosheet historical rows are never overwritten.
- **Probable starter upcoming game path (`compute_probable()`)**: Implemented via `mlb_baseball/sql/starter_workload_probable_update.sql`, reusing `latest_probable` (`_loaded_at DESC`) to ensure the latest snapshot wins over earlier announcements or scratches.
- **Strict point-in-time timeline safety**: Trailing workload and rest days aggregate pitcher history strictly before the target game's own date (`s.game_date < t.game_date`), eliminating leakage when probables are announced days ahead of an intervening start.
- **Comprehensive hand-computed regression tests**: Extended `tests/integration/test_model_starter_workload.py` with 6 new tests verifying hand-computed multi-start/relief 2026 lines, Retrosheet non-overwrite protection, latest probable / scratch resolution, table existence gates, and explicit leakage-safety proof exercising an announced-days-ahead-of-an-intervening-start scenario.
- **Bookkeeping and decisions**: Updated `docs/FEATURE_ADMISSION_QUEUE.md` (PIT-03 row fully closed with live/probable paths) and documented ADR-069 in `docs/DECISIONS.md`.

### Starter rest/workload (PIT-03) and PIT-04/PLN-01 admission closure (completed) — 2026-08-15

Completed two-part package closing admission-queue bookkeeping for PIT-04 and PLN-01, and implementing PIT-03 starter rest/workload (ADR-068):

- **Admission queue closures**: Verified and formally closed `PIT-04` (bullpen fatigue, ADR-039/042/051) and `PLN-01` (probable starter state, ADR-048) in `docs/FEATURE_ADMISSION_QUEUE.md` with cited commits and integration tests (`test_compute_gives_both_doubleheader_games_the_same_fatigue_value`, `test_compute_rolls_up_relief_only_with_zero_leakage_and_correct_fatigue_window`, `test_load_probable_appends_a_new_snapshot_on_a_scratch`, and `test_compute_probable_populates_upcoming_game_from_latest_announced_probable`).
- **PIT-03 starter rest/workload implementation**: Added `home_starter_rest_days`/`away_starter_rest_days` (integer) and `home_starter_outs_7d`/`away_starter_outs_7d` (numeric) via migration `0056_starter_workload.sql`, computed by `mlb_baseball/model/starter_workload.py` using `mlb_baseball/sql/starter_workload_retrosheet_update.sql`.
- **Reused ADR-042 day-collapse pattern**: Collapses all outs across appearances to pitcher-day grain before applying the window `RANGE` frame over trailing 7 calendar days, ensuring linear O(N) execution and unambiguous doubleheader peer-row resolution.
- **Hand-computed fixtures**: Comprehensive integration tests in `tests/integration/test_model_starter_workload.py` verified exact Decimal arithmetic matching a hand-calculated sequence modeled after Jacob deGrom's 2018 schedule, proving debut starts leave both columns NULL, rest days accurately diff consecutive start dates, relief appearances sum into 7d workload, and doubleheaders collapse correctly.
- **Scope discipline**: Retrosheet-historical path only (`compute()`). Live 2026 (`compute_live()`) and probable (`compute_probable()`) paths deferred as a recommended follow-up package.

### ML experiment lab code quality and dispatch structure pass (completed) — 2026-08-15

Completed code-quality, DevOps standards, and dispatch structure pass over the ML modeling harness (`mlb_baseball/model/experiment.py`, `feature_select.py`, `feature_select_stepwise.py`, and `mlb_baseball/cli.py`):

- **Dead code removal**: deleted unreachable and redundant `feature_select.py::health_check()` and associated unused `mlb_baseball.health` imports (`experiment.health_check()` and `feature_select_stepwise.health_check()` already comprehensively cover all experiment metadata tables).
- **Accurate module docstrings**: updated `experiment.py`'s module docstring to accurately describe its multi-target capabilities (classification and regression across calendar folds) and its role anchoring downstream feature selection.
- **Extracted CLI dispatch**: extracted `_run_experiment_command(args, conn)` from `main()` in `mlb_baseball/cli.py`, simplifying `main()` to a clean delegation call.
- **De-duplicated metric formatting**: unified classification (`log_loss`, `brier`) and regression (`mae`, `rmse`) formatting into `_format_metrics_line()`, shared across `experiment run` and `experiment compare`.
- **CLI dispatch test coverage**: added unit tests in `tests/unit/test_cli_dispatch.py` exercising real `cli.main()` dispatch for `experiment compare`, `experiment select-features`, `experiment select-features-stepwise`, and `experiment run` with regression metrics, verifying argument parsing, dead code removal, and byte-identical formatted output.
- **Full test suite, Ruff, and mypy pass clean**: verified zero regressions across all 773 tests and static analysis.

### Experiment lab failure bookkeeping fix, stepwise single-class guard, and doctor coverage (completed) — 2026-08-14

Fixed lost failure bookkeeping across the experiment lab, closed a single-class training split edge case in stepwise selection, and completed `mlb doctor` coverage under Plan 04E posture (`mlb_test` only, no production reads/writes):

- **Shared failure-bookkeeping helper (`_finalize_failed_run`)**: added private helper in `mlb_baseball/model/experiment.py` that executes `conn.rollback()`, executes the caller's failure SQL (`status = 'failed'`), and explicitly calls `conn.commit()`. Used across `experiment.py`, `feature_select.py`, and `feature_select_stepwise.py` before re-raising.
- **Root cause resolved**: fixes uncommitted failure records being wiped out by psycopg3's `Connection.__exit__` rollback when invoked through CLI context manager (`with get_connection() as conn:`).
- **Graceful single-class split guard**: in `feature_select_stepwise.py`, added verification that `inner_train_rows` contains at least two distinct class outcomes for classification targets. Single-class inner-training slices are recorded as `{"skipped": true, "reason": "single-class inner-training split"}` rather than crashing `LogisticRegression.fit`.
- **Operational doctor coverage**: wired `feature_select_stepwise.health_check()` directly into `mlb_baseball/doctor.py`, ensuring all three experiment-lab metadata tables (`meta.experiment_*`, `meta.feature_selection`, `meta.feature_selection_stepwise`) are reported by `mlb doctor`.
- **Verified ADR-067**: documented the exact failure mechanism, fix rationale, single-class telemetry, and doctor coverage.
- **Regression test suite**: tests in `test_experiment.py`, `test_feature_select.py`, and `test_feature_select_stepwise.py` reproduce real CLI context-manager failure paths and verify persistence without manual commits; new unit/integration tests verify the single-class skip path and doctor check reachability.

### Forward-stepwise feature selection with nested validation (stage 3) (completed) — 2026-08-14

Implemented Stage 3 of spec section 3 (feature selection) from `docs/superpowers/specs/2026-08-14-ml-modeling-harness-design.md` under Plan 04E posture (`mlb_test` only, no production reads/writes, purely diagnostic evidence):

- **New module (`mlb_baseball/model/feature_select_stepwise.py`)**: derives candidate features from the stage 1/2 stability report (`min_survival_fraction >= 0.70`), evaluates forward-stepwise search with nested chronological inner train/validate splits (train $\le T-2$, validate $T-1$) inside each outer fold ($\le T-1$).
- **Empty-inner-data handling**: graceful skip path for earliest folds (e.g. `season-2016` inner split needing $\le 2014$ data on a 2015-start history) recorded as `{"skipped": true, "reason": "insufficient inner-split data"}` without crashing or leaking.
- **Paired real-vs-shuffled control threshold**: at each forward step, tests baseline probe model (`logistic` / `ridge`) against both the real candidate feature column and a training matrix with the candidate column permuted via deterministic seed `int(_sha256(f"{seed}:{test_season}:{len(selected)}:{candidate}")[:15], 16)`. Candidate passes if and only if `real_score < shuffled_score`.
- **Greedy margin selection & stopping**: adds passing candidate with largest positive margin (`shuffled_score - real_score`) to selected set; terminates when no candidate beats its shuffled control.
- **Persistence (`meta.feature_selection_stepwise`)**: migration `0055_feature_selection_stepwise.sql` adds single-table persistence and content-addressed JSON artifact output (`artifacts/feature_selection_stepwise/<sha256>.json`). Deterministic `selection_id` (`fstep-<hash>`) ensures idempotency.
- **CLI (`mlb experiment select-features-stepwise --snapshot <id>`)**: discovers snapshot target, executes nested stepwise search, and prints candidate selection rates.
- **Verified ADR-066**: documents design choices, seed construction, and sibling module structure.
- **Verification**: synthetic unit tests prove paired shuffled control separates signal from noise and stops before noise features; integration tests verify classification and regression end-to-end execution, skip-path handling on `season-2016`, trace generation on `season-2017`/`2018`, DB idempotency, and CLI dispatch against `mlb_test`.

### Feature selection stability reporting (filter + embedded stages) (completed) — 2026-08-14

Implemented the first two stages of spec section 3 (feature selection) from `docs/superpowers/specs/2026-08-14-ml-modeling-harness-design.md` under Plan 04E posture (`mlb_test` only, no production reads/writes, purely diagnostic report):

- **New module (`mlb_baseball/model/feature_select.py`)**: produces a per-fold, per-candidate-feature stability report across the 11 `BASE_COLUMNS` candidate features.
- **Stage 1 (filter)**: permutation importance against a regularized linear baseline (`logistic` / `ridge`) evaluated against an injected standard normal control noise column (`__noise__`).
- **Stage 2 (embedded)**: tree-based feature importance from XGBoost (`xgboost` / `xgboost_regressor`) evaluated against the same injected noise column.
- **Survival criterion**: a feature survives a stage in a fold if and only if its importance strictly exceeds that of the injected control noise column in the same fit.
- **Persistence (`meta.feature_selection`)**: migration `0054_feature_selection.sql` adds single-table persistence and content-addressed JSON artifact output (`artifacts/feature_selection/<sha256>.json`). Deterministic `selection_id` (`fsel-<hash>`) ensures idempotency and fast reuse.
- **CLI (`mlb experiment select-features --snapshot <id>`)**: discovers the snapshot's target automatically and prints a per-feature cross-era survival summary table (`feature: stage1: k/n stage2: k/n both: k/n`).
- **Verified environment facts documented in ADR-065**:
  - Confirmed `HistGradientBoostingClassifier`/`Regressor` in installed `scikit-learn==1.9.0` do not expose `.feature_importances_` post-fit; XGBoost is used for the embedded stage.
  - Confirmed `xgboost==3.3.0` defaults `importance_type` to gain-based importance for `.feature_importances_`.
- **Deliberate scope cut**: Stage 3 (forward-stepwise wrapper with nested walk-forward CV) is deliberately deferred to avoid premature complexity and leakage risks before stages 1-2 provide proven survivor signals.
- **Verification**: unit tests prove synthetic signal vs noise separation across random seeds (10/10 true signal wins, <=1/10 noise false positives) and `selection_id` determinism; integration tests prove end-to-end classification and regression runs, idempotency, and CLI output against `mlb_test`.

### Target-agnostic experiment lab + run_differential (completed) — 2026-08-14

Implemented sections 1-2 of `docs/superpowers/specs/2026-08-14-ml-modeling-harness-design.md` under Plan 04B posture (`mlb_test` only, no production reads/writes, no promotion):

- **Target registry (`meta.experiment_target`)**: migration `0053_experiment_target_registry.sql` replaces hardcoded `CHECK (target = 'home_win')` on `meta.experiment_snapshot` and `meta.experiment` with foreign keys to `meta.experiment_target`. Seeded with `home_win` (classification) and `run_differential` (regression).
- **Snapshot uniqueness bug fix**: `meta.experiment_snapshot.row_sha256` constraint updated from bare `UNIQUE (row_sha256)` to `UNIQUE (row_sha256, target)`. `create_snapshot()` query updated to filter by `(row_sha256, target)`. Tested to prove identical rows produce separate, reusable snapshot IDs across targets.
- **Run differential regression models**: added baselines `zero` (0.0 margin) and `season_average` (`(home_runs_for - home_runs_allowed)/(home_wins + home_losses) - (away_runs_for - away_runs_allowed)/(away_wins + away_losses)` with divide-by-zero guards) plus ML regressors `ridge`, `hist_gradient_boosting_regressor`, and `xgboost_regressor`.
- **Regression metrics**: MAE and RMSE with 200-sample bootstrap 95% confidence intervals and decile predicted-value residual calibration.
- **CLI & compare**: `mlb experiment snapshot --target <name>`, `mlb experiment run --target <name> --model <name>`, and `mlb experiment compare` support both targets and format classification (log loss, brier) vs regression (mae, rmse) metrics cleanly.
- **Spec baseline corrections documented in ADR-064**: dropped preliminary unsourced Pythagenpat margin baseline; used season-average baseline computed from existing `BASE_COLUMNS`.
- **First-game-of-season null finding**: confirmed empirically that all 8 entering win/run columns are NULL on season openers, cleanly filtered by generic `required_columns` common-row selection.
- **Verification**: 311 unit and integration tests passed clean in pytest (including all 6 classification models, all 5 regression models, uniqueness, and metric determinism); Ruff and mypy passed 100% clean across all 68 source files.
- **Explicitly deferred**: feature selection (spec section 3), ensembles/stacking (section 5), Markov-derived features (section 4), neural models (section 6), and Parquet interoperability export (section 7).

### Production enrichment rollout, part 2 (completed) — 2026-08-14

Resumed exactly where the prior session paused, and finished it: every
enrichment module that had never run against production now has.

- **park**: `park.compute()` had already run with 4 rows flagged by its own
  health check. Root-caused by hand (read-only queries against `mlb`):
  venue 1604 ("South Side Park III") was the Chicago American Giants'
  Negro League home park 1913-1940 after the White Sox left in 1910, with
  as few as 1-11 games/season -- legitimately noisy small-sample park
  factors (33.33-290.00), not a bug.
- **team_rate**: first production run (216,592 rows: OBP/SLG/ISO/BB%/K%/
  BABIP/PA/run environment) after applying migration `0052_team_babip.sql`.
  All 10 health checks passed clean.
- **offense**: first production run, both historical and live paths
  (216,592/201,524 historical, 16,406/1,776 live rows: wOBA/wRC+). Surfaced
  one more verified small-sample case, same root cause as park's: the
  Philadelphia Stars (Negro League) had exactly one prior-1946 game with
  Retrosheet play-by-play coverage before their 1946-05-13 game -- hand
  calculation matches the stored wOBA to 13 decimal places. Both bounds
  widened with the verified real ranges, each with a new regression test
  (`41fe788`).
- **starter**: first production run, all 3 paths (201,524 historical +
  1,776 live + 36 probable rows). Clean on the first try: the 13,613-
  pitcher-season reconciliation against `raw.bref_pitching` landed at 1.7%
  mismatch, inside its documented 2.0% accepted rate. Also synced a stale
  citation in its docstring with `docs/RESEARCH.md`'s 2026-08-13 correction
  (`7b4c4e2`), noticed while reading it before running.
- **bullpen**: first production run, all 3 paths (216,592 + 15,264 +
  748 rows). Clean: 406,516-row starter/bullpen outs-split reconciliation
  passed exactly.
- **oaa**, **speed**, **framing**, **war**: first production runs
  (216,592 rows each). All clean, no anomalies.

Full suite: 735 passed, 1 skipped; ruff/mypy/sqlfluff clean throughout.
Every read/write step stated its target database explicitly before running,
per CLAUDE.md's database-naming golden rule.

### Team prior BABIP (OFF-04, ADR-063) — 2026-08-14 (test database only)

- Migration `0052_team_babip.sql` adds nullable `home_babip` and `away_babip` columns to `gold.game_feature`.
- `team_rate_retrosheet_update.sql` and `team_rate.py` implement point-in-time BABIP entering each regular-season game: $(H - HR) / (AB - K - HR + SF)$ with a documented minimum balls-in-play gate (`MIN_BIP = 8`).
- Integration tests in `tests/integration/test_model_team_rate.py` verified exact hand-calculated Decimal arithmetic ($7/11$ BABIP when $BIP=11$, NULL when $BIP < 8$), full suite of 10 tests passed against `mlb_test`. Full unit suite (289 passed in 2.7s), Ruff, mypy, and SQLFluff all clean. `docs/FEATURE_ADMISSION_QUEUE.md` updated and ADR-063 recorded.

### Developer environment & linting posture — 2026-08-14

- Added complete portable `.devcontainer` configuration (`devcontainer.json`, `docker-compose.yml`, `Dockerfile`, and `post-create.sh`) supporting VS Code and GitHub Codespaces with Python 3.11, PostgreSQL 16 (`pg_stat_statements` enabled), and Chadwick C-tools (`cwevent`, `cwgame`, `cwbox`) built from source.
- Added `.pre-commit-config.yaml` to enforce Ruff formatting/linting, mypy static typing, and SQLFluff validation on local commits.
- Verified test suite baseline: 289 unit tests passing in 3.35s; Ruff, SQLFluff, and mypy checks clean.

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

### Plan 01F production cutover executed — 2026-08-18

- Migrations `0040`–`0056` applied to production `mlb` (previously verified
  only in `mlb_test` per the R1-R6 rehearsal evidence above). `mlb migrate`
  needed a new `--skip` flag to sequence around a real forward dependency:
  `0040`'s `core.game.game_pk` unique index couldn't apply until `mlb
  conform` deduplicated existing data, but the code path `conform` needed
  to do that safely (`retro_game_id` nullable) was added in `0045`, after
  `0040` in file order.
- Root-caused the actual duplicate-`game_pk` defect blocking `0040`:
  `_backfill_game_pk_via_exact_final_score` (`conform.py`) could assign an
  already-claimed MLB `game_pk` to a doubleheader partner with an
  identical score — found via a real production case (1941-09-14
  Homestead Grays @ Newark Eagles, both games 6-4, only game 2 had a
  published `gamePk`). Fixed with a `NOT EXISTS` guard against
  already-claimed keys; regression test reproduces the exact scenario.
  1,135 production duplicates (concentrated 1901-1909, one 1941 case) →
  0 after rebuild.
- `mlb backfill-game-identities` run to completion against production
  first (per `0036`'s own precondition), then `mlb conform` rebuilt
  `core`/`gold` (~30M rows), `mlb features`/`mlb report`/`mlb predict` run
  to populate the previously-empty `gold.game_feature`,
  `gold.player_season`, `gold.team_season`, `gold.division_standing`.
- **Acceptance gate evidence, production `mlb`, post-cutover:**
  - `mlb audit --scope game`: 0 duplicate populated `game_pk` values, 0
    doubleheader-identity collisions, 24/28 checks PASS (remainder SKIP —
    expected, no experiment snapshots yet).
  - `mlb doctor`: 182/192 checks passing (up from 137/163 pre-cutover).
    Remaining fails are pre-existing, unrelated gaps (never-bootstrapped
    Kalshi/Polymarket intraday-price tables, a stale 2026-08-16
    `retrosheet_box` run, 1950s `mlb_api` analytics coverage) — not new
    regressions from this cutover.
  - `SELECT count(*) FROM (SELECT game_pk FROM core.game WHERE game_pk IS
    NOT NULL GROUP BY game_pk HAVING count(*) > 1) d` → `0`.
- A second, independent gap found and fixed along the way: this host's
  cron silently missed the entire daily pipeline (`mlb update` →
  `mlb conform` → `mlb predict`, including Kalshi/Polymarket) for two days
  after a mid-cron-slot reboot, with zero `meta.ingestion_run` row and zero
  `mlb doctor` signal — `check_recent_run` (mlb_api's existing 15-minute
  freshness check) had never been extended to the daily-cadence
  connectors/`conform`/`predict`. Now added everywhere it applies, scoped
  by `meta.ingestion_run.mode` where a `SOURCE` is shared across a
  scheduled and an unscheduled mode (e.g. kalshi's daily `update` vs.
  owner-triggered `backfill`).
- All work merged to `main` via PR #14 (squash-merged as `7fd9e7a`), after
  resolving a real conflict with a concurrently-merged PR #13 (GitHub
  branch-protection rollout) that independently landed an unrelated,
  narrower fix in the same area (removing the daily-freshness check from
  three genuinely seasonal sources — bref/statcast/statcast_leaderboard —
  whose own docstrings already say they don't change intra-day).
- **This closes the specific blocker cited by every "dormant until wired"
  enrichment family since 2026-08-07** (see `team_prior_offense_defense_v1`
  above, 2026-08-12/13). Plan 01F's remaining acceptance-gate items
  (consumer/workflow-overlap tests, `public_safe` rights enforcement) are
  unaffected by this change and remain open; this entry closes only the
  production-cutover portion of R2 that every later item was blocked
  behind.

### Plan 04C — random forest / extra trees model families — 2026-08-18 (`mlb_test` only)

- Added `random_forest`/`extra_trees` (classifier, `home_win`) and
  `random_forest_regressor`/`extra_trees_regressor` (regressor,
  `run_differential`) to `mlb_baseball/model/experiment.py`'s
  `TARGET_REGISTRY`, `SUPPORTED_MODELS`, `_make_estimator`, and
  `_validate_parameters` — the next explicitly-named, entirely
  unimplemented family from Plan 04C's model list (regularized regression,
  gradient boosting, and now random forests/extra trees are built; SVMs,
  Bayesian/hierarchical, GAM, and neural/sequence models remain open).
  Followed `docs/EXPERIMENT_RUNBOOK.md`'s own documented "Add a model or
  target" procedure exactly: no new files, no model-specific training
  script, reused the shared snapshot/fold/scoring/artifact path.
  `_probabilities`/`_predictions` needed no changes — both already
  dispatch generically to `_make_estimator` + `predict_proba`/`predict`
  for anything past their own hardcoded baselines (`_probabilities` has
  three — `home_rate`/`log5`/`elo`; `_predictions` has two —
  `zero`/`season_average`), and RandomForest/ExtraTrees both support
  `predict_proba` natively.
- `tests/integration/test_experiment.py`'s two existing tests
  (`test_all_supported_models_share_calendar_rehearsal_rows`,
  `test_run_differential_models_share_calendar_rehearsal_rows`) are
  parametrized over `SUPPORTED_MODELS`/`valid_model_families`, so the four
  new families got full idempotency/fold-structure/no-leakage coverage
  automatically (17 -> 21 passing). Added targeted `_validate_parameters`
  unit coverage for all four (`tests/unit/test_experiment_metrics.py`) and
  fixed the one hardcoded `run_differential` family-list assertion.
- **Real production-shaped verification, not just the small `mlb_test`
  fixture**: loaded a 640-game real sample (100 games/season, 2015-2024,
  via `mlb_baseball.rehearsal.load_sample`'s existing read-only-on-source
  path) into `mlb_test`, ran `mlb conform`/`mlb features`, then ran every
  `home_win` model family (`home_rate`, `log5`, `elo`, `logistic`,
  `hist_gradient_boosting`, `random_forest`, `extra_trees`) and every
  `run_differential` family through `mlb experiment run`/`compare`.
  `random_forest`/`extra_trees` produced plausible log-loss (0.67-0.83,
  same range as the other real model families) on this honest small
  sample — worse than the transparent `home_rate`/`elo` baselines, which
  is the expected, non-suspicious result on this little data (per
  `docs/RESEARCH.md`'s own calibration doctrine: beating simple baselines
  on a small sample is a leakage red flag, not a win to celebrate).
  `extra_trees` was noisier than `random_forest` (log-loss up to 2.97 in
  one fold) — a known real property of its extra-random split selection
  on small samples, not a bug. Re-running the identical config correctly
  returned `(reused)` with byte-identical metrics (idempotency, verified,
  not assumed).
- **Found and fixed a real, pre-existing bug along the way, not
  hypothetical**: `log5.probability()` divides 0/0 whenever both teams'
  win percentages are equal at exactly 0 or exactly 1 — confirmed via two
  distinct real cases in the above production sample (two genuine
  still-winless 2018/2020 teams, 0-2 and 0-1; and three genuine
  still-undefeated 2019/2020/2023 team pairs, up to 4-0). The function's
  old docstring claimed the 0/0 case "can't happen for a team with at
  least one prior game," which is simply false — a winless-or-undefeated
  team's record is a real, common early-season state, and this rehearsal
  sample's shallow per-team-game counts (not a deep multi-decade sample)
  made it common enough to hit directly rather than needing an edge-case
  hunt. Fixed by returning `0.5` for both cases — verified this is the
  same limiting value the formula already returns for two *equal* teams
  at every other winning percentage, not an arbitrary guess. Two new
  regression tests in `tests/unit/test_log5_formula.py` (7 passing, up
  from 5) reproduce both cases directly. This bug pre-dates today's work
  entirely and would affect `log5.predict()`'s real production
  predictions and `gbm.py`'s use of the same function too, not just the
  experiment lab -- not scoped further here (out of scope for this
  package), but worth an owner-authorized production re-check of
  `gold.prediction` for any historical `log5-v2` row keyed to a genuinely
  winless-or-undefeated matchup.
- `uv run ruff check .` clean. Full relevant suite:
  `tests/integration/test_experiment.py` (21), `test_model_log5.py` (3),
  `test_model_gbm.py` (9), `tests/unit/test_experiment_metrics.py` (7),
  `tests/unit/test_log5_formula.py` (7), `tests/unit/test_cli_dispatch.py`
  experiment subset (6) — 53 passed, 0 failed. Rehearsal sample cleared
  via `CLEAR_REHEARSAL_SAMPLE=1` before the final clean run, per
  `docs/CONFORMANCE_REHEARSAL.md`'s own documented boundary. No production
  `mlb` write occurred -- the real-data verification pulled read-only from
  `mlb` (source transaction explicitly `SET TRANSACTION READ ONLY`) into
  `mlb_test` only, same safety pattern `scripts/rehearse_sample.py` already
  established.
- Not wired into any production path -- matches every sibling model
  family's own dormant-until-a-separate-promotion-decision posture. No
  champion/challenger comparison or promotion decision was made; this
  package only proves the two families work correctly end-to-end and
  produce honest, plausible metrics on real data.

### Plan 04C — GAM model family — 2026-08-18 (`mlb_test` only)

- Added `gam` (classifier, `home_win`) and `gam_regressor` (regressor,
  `run_differential`) to `mlb_baseball/model/experiment.py`'s
  `TARGET_REGISTRY`, `SUPPORTED_MODELS`, `_make_estimator`, and
  `_validate_parameters` -- the next explicitly-named, entirely
  unimplemented family from Plan 04C's model list (regularized regression,
  gradient boosting, random forest/extra trees were already built; SVMs,
  Bayesian/hierarchical, and neural/sequence models remain open). No new
  dependency: a GAM is mathematically a linear model fit over
  spline-expanded features, so both families reuse `logistic`/`ridge`'s
  exact pipeline shape with one added step --
  `SimpleImputer(strategy="median", add_indicator=True)` ->
  `SplineTransformer(degree=3, n_knots=5)` -> `StandardScaler()` ->
  `LogisticRegression`/`Ridge` -- ordered so the spline transform (which
  rejects NaN input) always runs after imputation, matching this file's
  existing ordering discipline. `gam` reuses `logistic`'s defaults
  (`max_iter=1_000`, `random_state=seed`); `gam_regressor` reuses
  `ridge`'s (`random_state=seed`). `_validate_parameters` checks `gam`
  against `LogisticRegression().get_params(deep=False)` and
  `gam_regressor` against `Ridge().get_params(deep=False)`, in their own
  `elif` branches per this file's per-family-string dispatch convention.
  `_probabilities`/`_predictions` needed no changes -- both already
  dispatch generically to `_make_estimator` + `predict_proba`/`predict`
  for anything past their own hardcoded baselines.
- `tests/integration/test_experiment.py`'s two existing tests
  (`test_all_supported_models_share_calendar_rehearsal_rows`,
  `test_run_differential_models_share_calendar_rehearsal_rows`) are
  parametrized over `SUPPORTED_MODELS`/`valid_model_families`, so both new
  families got full idempotency/fold-structure/no-leakage coverage
  automatically with zero test-file changes needed (82 passed total in
  this targeted suite, up from the file's baseline). Added targeted
  `_validate_parameters` and override-effect unit coverage for both in
  `tests/unit/test_experiment_metrics.py` (its estimator-override test
  and its `run_differential` `valid_model_families` spec assertion are
  both hardcoded lists there, not dynamic, so `gam`/`gam_regressor` were
  added to both explicitly). Grepped the repo for any other hardcoded
  model-family list (CLI dispatch, docs generation) that might need a
  matching update -- `mlb_baseball/cli.py`'s `--model` argument already
  uses `choices=experiment.ALL_MODEL_FAMILIES` (dynamic), so no change was
  needed there; also updated `docs/EXPERIMENT_RUNBOOK.md`'s prose model
  list in the same change for consistency.
- **Real production-shaped verification, not just the small `mlb_test`
  fixture**: loaded a 640-game real sample (100 games/season, 2015-2024,
  via `mlb_baseball.rehearsal.load_sample`'s existing read-only-on-source
  path) into `mlb_test`, ran `mlb conform`/`mlb features`, then ran every
  `home_win` model family (`home_rate`, `log5`, `elo`, `logistic`,
  `hist_gradient_boosting`, `random_forest`, `extra_trees`, `gam`) and
  every `run_differential` family (`zero`, `season_average`, `ridge`,
  `gam_regressor`) through `mlb experiment run`/`compare`. `gam` produced
  finite log-loss across the nine 2016-2024 folds (0.6992-1.8681, Brier
  0.2520-0.4579) -- in the same noisy-but-sane range as `random_forest`
  (0.6785-0.8305) and `extra_trees` (0.7667-2.9670) on this small sample,
  worse than the transparent `home_rate`/`elo` baselines on several
  folds, which is the expected non-suspicious result on this little data
  (per `docs/RESEARCH.md`'s own calibration doctrine: beating simple
  baselines on a small sample is a leakage red flag, not a win to
  celebrate). `gam_regressor` produced finite MAE (3.7522-7.9090) and
  RMSE (4.7706-10.3353) across the same folds, in the same range as
  `season_average` (MAE 4.3896-7.0316, RMSE 5.3632-8.9434). No NaN/inf,
  no crash, and no convergence warning was observed at `n_knots=5` on
  this sample size. An independent Gemini review pass flagged, and direct
  verification confirmed, that `SimpleImputer(add_indicator=True)`'s
  binary missing-value indicator columns are *not* passed through
  `SplineTransformer` unchanged as first assumed -- it spline-expands
  every input column indiscriminately (confirmed: 13 input columns ->
  91 output columns at `degree=3, n_knots=5`), so each indicator becomes
  7 redundant, collinear dummy columns rather than staying a single 0/1
  feature. This does not break anything -- the real-data run above stayed
  finite and plausible, and `LogisticRegression`/`Ridge`'s L2 penalty
  absorbs the collinearity -- but it is real, avoidable dimensionality
  waste, documented as a "Revisit if" item in ADR-072 rather than fixed
  here (fixing it needs a `ColumnTransformer` to route indicator columns
  around the spline step, a real architectural change to the shared
  impute -> transform -> scale -> model pipeline shape, not a one-line
  fix). Re-running each identical config correctly returned
  `(reused)` with byte-identical metrics (idempotency, verified, not
  assumed). Rehearsal sample cleared via `CLEAR_REHEARSAL_SAMPLE=1` before
  the final clean test run, per `docs/CONFORMANCE_REHEARSAL.md`'s own
  documented boundary. No production `mlb` write occurred -- the
  real-data verification pulled read-only from `mlb` (source transaction
  explicitly `SET TRANSACTION READ ONLY`) into `mlb_test` only, same
  safety pattern `scripts/rehearse_sample.py` already established.
- `uv run ruff check .` clean and `uv run ruff format --check .` clean on
  every file touched by this change (`mlb_baseball/model/experiment.py`,
  `tests/unit/test_experiment_metrics.py`, `docs/EXPERIMENT_RUNBOOK.md`).
  The repo-wide `ruff format --check .` also reports pre-existing
  unformatted files unrelated to this change (confirmed via `git stash`
  before touching anything) -- an environment/ruff-version drift from an
  earlier session, not introduced or touched here. `uv run mypy
  mlb_baseball/model/experiment.py` clean. Full relevant suite:
  `tests/integration/test_experiment.py`, `tests/unit/test_experiment_metrics.py`,
  `tests/unit/test_cli_dispatch.py` -- 82 passed, 0 failed, run twice
  (once against the loaded rehearsal sample, once after clearing it).
- Not wired into any production path -- matches every sibling model
  family's own dormant-until-a-separate-promotion-decision posture. No
  champion/challenger comparison or promotion decision was made; this
  package only proves the two families work correctly end-to-end and
  produce honest, plausible metrics on real data.

### Issue #6 (bref mojibake) and issue #9 item 6 (bat_event_fl + doubleheader ordering) — 2026-08-18

Two bug-fix PRs closing real, previously-open issues:

- **PR #24 (issue #6, merged `f913ff6`):** `raw.bref_batting`/`raw.bref_pitching.name`
  stored non-ASCII player names as literal escaped garbage instead of real
  UTF-8. Root-caused by reading `pybaseball`'s own source, not guessed:
  `batting_stats_bref()`/`pitching_stats_bref()` scrape HTML via `get_soup()`,
  which calls `str(response.content).encode()` -- `str()` on raw HTTP
  response `bytes` produces `bytes.__repr__()` text instead of decoding it,
  so every accented name comes back as its own backslash-escaped repr.
  Reproduced byte-for-byte against a real `pybaseball.batting_stats_bref(2023)`
  call (59/660 rows mangled) and `pitching_stats_bref(2023)` (75/863 mangled);
  0 mangled after the fix. `pybaseball.bwar_bat()`/`bwar_pitch()` take a
  different, correct decode path and were confirmed clean (0 of
  126,478/57,686 rows). Fixed via a new `_repair_name_mojibake()` in
  `mlb_baseball/connectors/bref.py`, applied to the `Name` column only
  before loading. See ADR-071. Only fixes rows loaded from this point
  forward -- existing production `mlb` rows still carry the old mangled
  names until an owner-authorized forced reload or repair `UPDATE`, not
  done as part of this fix.
- **PR #25 (issue #9 item 6, merged `cfa84d7`):** `team_woba_retrosheet_update.sql`
  and `team_wrc_plus_retrosheet_update.sql` predated ADR-034's finding
  (`team_rate_retrosheet_update.sql`'s `db97d96` fix) that every `event_cd`
  count from `raw.retrosheet_event` must be gated on `bat_event_fl = 'T'`.
  Fixed both. Auditing every retrosheet-event SQL file for the same pattern
  also found the identical doubleheader-ordering bug `db97d96` fixed in
  `team_rate` (rolling window ordered same-date rows by `game_id`, an
  insertion-order serial, not the declared `game_number`) independently
  present in `team_woba`, `team_wrc_plus`, and a fourth occurrence in
  `team_bullpen_retrosheet_update.sql`'s quality window (not named in
  issue #9's text) -- fixed all four.
- **Real review value, not just process:** PR #25's review round caught a
  genuine P1 bug in the doubleheader-ordering fix itself, independently
  flagged by three reviewers (chatgpt-codex-connector, coderabbitai,
  codeant-ai): `team_wrc_plus_retrosheet_update.sql`'s window is
  season-wide (every team pooled together), so `game_number` alone is not
  a safe tiebreak there the way it is in `team_rate`/`team_woba`/`team_bullpen`'s
  team-partitioned windows -- `game_number` only means "which game of THIS
  matchup's doubleheader," and carries no relationship to a different
  matchup sharing the same `game_date`. Fixed by sorting on
  `home_team_id`/`away_team_id` before `game_number`, so `game_number` only
  ever disambiguates two rows already known to be the same matchup.
  Verified directly: reverted the fix, confirmed the extended regression
  test (an unrelated same-date game with a colliding `game_number` and a
  distinctive HR event) fails with the exact wrong value
  (`130.902777777778` instead of `144.1666666666667`), restored the fix.
  Two narrower findings from the same review round were real but
  out-of-scope for this PR and tracked separately rather than patched in:
  issue #28 (a data-quality edge case in the already-established
  `game_number NULLS LAST` pattern, shared by all 4 team-partitioned files,
  not new to this PR) and issue #29 (`team_bullpen`'s pre-existing
  zero-fill backbone for Retrosheet-uncovered games, predates this PR).
- Full relevant suite green: `test_model_offense.py`, `test_model_wrc_plus.py`,
  `test_model_bullpen.py` -- 27 passed; `test_model_team_rate.py`,
  `test_model_starter.py`, `test_model_starter_workload.py` (unaffected,
  checked for regressions) -- 35 passed. `ruff check .` clean,
  `sqlfluff-lint` (pre-commit hook) passed on all touched SQL.
- Not wired into any production path beyond what was already running --
  these are correctness fixes to already-deployed enrichment SQL
  (`offense.py`/`bullpen.py`), not new features.

### Plan 04C — SVM model family — 2026-08-18 (`mlb_test` only)

- Added `svm` (classifier, `home_win`) and `svm_regressor` (regressor,
  `run_differential`) to `mlb_baseball/model/experiment.py` --
  `TARGET_REGISTRY`, `SUPPORTED_MODELS`, `_make_estimator`,
  `_validate_parameters`. The last explicitly-named Plan 04C model family
  still entirely unbuilt: regularized regression, gradient boosting,
  random forest/extra trees (2026-08-18 earlier this same day), and GAM
  (2026-08-18) were already built; only Bayesian/hierarchical and
  neural/sequence/embedding models remain open. `svm` is
  `impute -> scale -> SVC(kernel="rbf", probability=True,
  random_state=seed)`, matching `logistic`'s scaled-pipeline shape.
  `svm_regressor` is `impute -> scale -> SVR(kernel="rbf")` matching
  `ridge`'s shape, with no `random_state` (scikit-learn's `SVR` has no
  such constructor parameter at all, unlike `Ridge`) and no `probability`.
- **A real, tracked future-breakage point, not silently ignored:**
  `SVC(probability=True)` is required for `predict_proba` (every family
  past the three hardcoded baselines needs it), but scikit-learn 1.9 (the
  version pinned here) deprecated that constructor argument in favor of
  `CalibratedClassifierCV(SVC(), ensemble=False)`, removal targeted for
  1.11. Deliberately not switched to that wrapper yet: it would push every
  tunable SVM parameter behind an `estimator__` prefix in
  `get_params(deep=False)`, breaking this file's established flat-pipeline
  `_validate_parameters` convention every other family follows. Documented
  as a "Revisit if" item in ADR-073 and a code comment at the `svm` branch
  rather than left as a silent trap for a future scikit-learn upgrade.
- **PR review found and fixed a real bug: `probability=False` was silently
  accepted, then crashed mid-run.** `probability` is a genuine `SVC`
  constructor parameter, so `_validate_parameters`'s generic allowed-set
  check let a `{"probability": False}` override straight through -- but
  `_probabilities()` unconditionally calls `predict_proba`, which `SVC`
  only exposes when `probability=True` (confirmed directly:
  `SVC(probability=False).predict_proba(...)` raises `AttributeError`).
  Fixed with an explicit rejection in `_validate_parameters`, covered by
  a new regression test.
- **Investigated and declined a P1 review claim that `SVC`'s internal
  calibration violates the chronological-folds doctrine.** `SVC`'s
  Platt-scaling calibration uses a random 5-fold split, but only ever
  over the *already fully chronologically-isolated training set* --
  `AGENTS.md`'s "rolling-origin and nested validation" requirement
  governs the experiment lab's own outer train-through-season/test-season
  boundary, which this never touches. Same category of internal,
  in-training-set-only randomness as `RandomForestClassifier`'s bootstrap
  resampling. Declined building a custom chronological calibrator (no
  such thing exists in scikit-learn) to close a leakage path that isn't
  actually open.
- **Added a documentation caveat (not a code-level cap) for SVM's
  sample-size sensitivity**, per review and `AGENTS.md`'s own "SVMs where
  dataset size permits" scoping -- `docs/EXPERIMENT_RUNBOOK.md` now flags
  `svm`/`svm_regressor`'s quadratic-ish scaling explicitly. No enforced
  row-count cap: no sibling family has one either, matching this file's
  "document a known limitation, don't pre-engineer for it" posture.
- **Verified against real production-shaped data, not just the small
  `mlb_test` fixture -- and respecting the reserved 2025 final holdout:**
  loaded a bounded multi-season real sample (10 games/season across
  2008/2015/2024/2025/2026, via `mlb_baseball.rehearsal.load_sample`'s
  existing read-only-on-source path) into `mlb_test`, ran `mlb conform`/
  `mlb features`, then ran both new families through `mlb experiment run`
  with `--fold-years 2015 2024` specifically -- **not** the sample's full
  span, since `plans/04-modeling-simulation-and-experiments.md` reserves
  2025 as an untouched final holdout and 2026 for forward monitoring (an
  initial verification pass mistakenly included both; caught in PR
  review, re-run correctly before merge). `svm` produced finite,
  plausible log-loss (0.65-0.73) and Brier (0.23-0.26), in the same range
  as `home_rate`'s own baseline (log-loss 0.51-0.78) -- not a suspicious
  "beats every baseline" result. `svm_regressor` produced finite MAE
  (3.27-3.70) and RMSE (4.34-4.38), noticeably better than
  `season_average`'s baseline (MAE 7.88-8.99) on this small sample -- per
  `docs/RESEARCH.md`'s own calibration doctrine this pattern would be a
  leakage red flag on a *larger* sample, but `svm_regressor` uses the
  identical `BASE_COLUMNS` feature set every other regression family
  already uses (no new or different data access), and beating a naive
  baseline by chance on a ~10-game/season sample is unsurprising --
  noted honestly rather than over-claimed. Re-running each identical
  config correctly returned `(reused)` with byte-identical metrics
  (idempotency, verified, not assumed). Rehearsal sample cleared via
  `CLEAR_REHEARSAL_SAMPLE=1` before the final clean test run. No
  production `mlb` write occurred -- pulled read-only from `mlb` into
  `mlb_test` only.
- `uv run ruff check .` clean, `uv run ruff format --check .` clean on
  every file touched, `uv run mypy mlb_baseball/model/experiment.py`
  clean. Full relevant suite: `tests/integration/test_experiment.py`,
  `tests/unit/test_experiment_metrics.py`, `tests/unit/test_cli_dispatch.py`
  -- 86 passed (plus the new `probability=False` regression test), 0
  failed, run twice (once against the loaded rehearsal sample, once
  after clearing it).
- `svm_regressor` needed its own dedicated override-effect test
  (`test_make_estimator_lets_a_valid_svm_regressor_override_take_effect`,
  using `C` as the override parameter) rather than joining the existing
  parametrized test the other 8 families share, since that test overrides
  `random_state` specifically and `SVR` has no such parameter to override.
- Not wired into any production path -- matches every sibling model
  family's own dormant-until-a-separate-promotion-decision posture. No
  champion/challenger comparison or promotion decision was made.

### Plan 04C -- Bayesian model family -- 2026-08-19 (`mlb_test` only)

- Added `bayesian` (classifier, `home_win`, `GaussianNB`) and
  `bayesian_regressor` (regressor, `run_differential`, `BayesianRidge`) to
  `mlb_baseball/model/experiment.py` -- `TARGET_REGISTRY`,
  `SUPPORTED_MODELS`, `_make_estimator`, `_validate_parameters`, following
  the same branch-per-family pattern as every prior 04C family. Both are
  genuinely Bayesian (Bayes' rule applied directly), not new-dependency
  approximations: `GaussianNB` is scikit-learn's own Bayesian classifier,
  `BayesianRidge` places explicit priors on weights/noise precision and
  fits them by deterministic iterative evidence maximization (not a
  single-shot closed form -- analytic updates each round, repeated until
  convergence or `max_iter`). Neither has a `random_state` parameter --
  neither has internal randomness to seed, the same situation
  `svm_regressor` was in with `SVR`.
- **Real scope gap, made explicit rather than silently claimed closed:**
  Plan 04C names "Bayesian/hierarchical approaches" as one family, but
  they are different techniques. True hierarchical/multilevel
  (partial-pooling) models need `statsmodels` or a probabilistic-
  programming library, neither of which is in `pyproject.toml` -- adding
  one is a real dependency decision, not made here. Plan 04C's own status
  line now says "true hierarchical/multilevel (partial-pooling) and
  neural/sequence/embedding models" specifically, not "Bayesian/
  hierarchical" as one bucket, so this stays visible as still-open work.
  See ADR-074.
- **A real, honestly-documented finding: `bayesian` was badly
  miscalibrated on the small rehearsal sample, not hidden or smoothed
  over.** `--fold-years 2015 2024`: `season-2015` log loss was exactly
  `0.0000` (confidently and correctly certain on every test-fold game),
  but `season-2024` was `14.4175` -- one confidently wrong call is
  catastrophic under log loss. Root cause: `GaussianNB` has no
  regularization on its per-class Gaussian variance estimates beyond a
  tiny `var_smoothing` term, so a near-zero variance estimate on a tiny
  per-class training fold can produce near-0/near-1 posterior
  probabilities. Documented as a caveat in `docs/EXPERIMENT_RUNBOOK.md`;
  no code-level cap added, matching this file's established "document,
  don't pre-engineer for" posture for a dormant family.
- **Verified against real production-shaped data, not just the small
  `mlb_test` fixture -- and respecting the reserved 2025 final holdout:**
  loaded a bounded multi-season real sample (10 games/season across
  2008/2015/2024/2025/2026) into `mlb_test`, ran `mlb conform`/
  `mlb features`, then ran both new families through `mlb experiment run`
  with `--fold-years 2015 2024` specifically (2025 stays the untouched
  final holdout, 2026 forward monitoring only). `bayesian_regressor`
  produced finite MAE (3.72-5.44) and RMSE (4.11-6.38), better than
  `season_average`'s baseline (MAE 7.88-8.99) on this small sample --
  same "uses the identical `BASE_COLUMNS` every other regressor already
  uses, not a leakage red flag" honest caveat as every prior regressor
  family here. Re-running each identical config correctly returned
  `(reused)` with byte-identical metrics. Rehearsal sample cleared before
  the final clean test run. No production `mlb` write occurred.
- `uv run ruff check .` clean, `uv run ruff format --check .` clean on
  every file touched, `uv run mypy mlb_baseball/model/experiment.py`
  clean. Full relevant suite: `tests/integration/test_experiment.py`
  (27 passed), `tests/unit/test_experiment_metrics.py` (24 passed,
  including 4 new tests), `tests/unit/test_cli_dispatch.py` and
  `tests/integration/test_ingest_tracking.py` (50 passed, regression
  check) -- 361 passed total, run twice (once against the loaded
  rehearsal sample, once after clearing it).
- `bayesian`/`bayesian_regressor` each needed their own dedicated
  override-effect test (`var_smoothing` and `alpha_1` respectively),
  excluded from the existing parametrized `random_state`-override test
  the same way `svm_regressor` was, since neither estimator has a
  `random_state` parameter.
- Not wired into any production path -- matches every sibling model
  family's own dormant-until-a-separate-promotion-decision posture. No
  champion/challenger comparison or promotion decision was made.

### Plan 04C -- neural model family -- 2026-08-19 (`mlb_test` only)

- Added `neural` (classifier, `home_win`, `MLPClassifier`) and
  `neural_regressor` (regressor, `run_differential`, `MLPRegressor`) to
  `mlb_baseball/model/experiment.py` -- `TARGET_REGISTRY`,
  `SUPPORTED_MODELS`, `_make_estimator`, `_validate_parameters`, following
  the same branch-per-family pattern as every prior 04C family. Both are
  genuinely neural (feedforward network, backprop-trained weights), not a
  relabeled linear model the way `gam` is -- `sklearn.neural_network`
  ships this already, no new dependency. `max_iter` raised from
  scikit-learn's default 200 to 1,000 (the same fix `logistic`/`gam`
  already apply). Both take `random_state` (weight init + `solver="adam"`
  stochasticity), so both join the existing shared parametrized
  override-effect test directly -- no dedicated override test needed,
  unlike `svm_regressor`.
- **Real scope gap, made explicit rather than silently claimed closed:**
  Plan 04C names "neural/sequence/embedding models" as one family, but
  they are different techniques. True sequence models (RNN/LSTM/
  attention) need a sequential feature representation this project
  doesn't have (`game_base_v1` is a flat per-game vector) and almost
  certainly a new dependency (PyTorch/TensorFlow/JAX), neither of which
  is added here. Plan 04C's own status line now names this gap
  specifically rather than bundling it under "neural" as closed. See
  ADR-075.
- **A real, honestly-documented finding: both new families performed
  clearly worse than their transparent baselines on the small rehearsal
  sample, not hidden.** `--fold-years 2015 2024`: `neural`'s log loss
  (2.04-2.09) was far worse than `home_rate`'s (0.51-0.78);
  `neural_regressor`'s MAE (8.61-9.86) was worse than `season_average`'s
  (7.88-8.99). The training sets were smaller than "rehearsal sample"
  suggests -- confirmed directly by querying `mlb_test`, not assumed:
  `season-2015`'s training fold had exactly 10 `gold.game_feature` rows,
  `season-2024`'s had exactly 20 (the rehearsal's `games_per_season=10`
  bound narrows historical seasons this far even though `core.game`
  itself has the full season; see `docs/EXPERIMENT_RUNBOOK.md`). A
  100-unit hidden-layer network fit on 10-20 rows makes severe
  overfitting close to guaranteed, which is the expected, non-suspicious
  outcome per `docs/RESEARCH.md`'s own calibration doctrine -- a small
  sample where `neural` unexpectedly *beat* every baseline would be the
  result worth distrusting instead. No convergence warning observed
  (rehearsal sample or a larger synthetic 400-row check); `max_iter=1_000`
  appears sufficient at this scale, documented as a caveat in
  `docs/EXPERIMENT_RUNBOOK.md`.
- **Verified against real production-shaped data, not just the small
  `mlb_test` fixture -- and respecting the reserved 2025 final holdout:**
  loaded a bounded multi-season real sample (10 games/season across
  2008/2015/2024/2025/2026) into `mlb_test`, ran `mlb conform`/
  `mlb features`, then ran both new families through `mlb experiment run`
  with `--fold-years 2015 2024` specifically (2025 stays the untouched
  final holdout, 2026 forward monitoring only). Re-running each identical
  config correctly returned `(reused)` with byte-identical metrics.
  Rehearsal sample cleared before the final clean test run. No
  production `mlb` write occurred.
- `uv run ruff check .` clean, `uv run ruff format --check .` clean on
  every file touched, `uv run mypy mlb_baseball/model/experiment.py`
  clean. Full relevant suite: `tests/integration/test_experiment.py`
  (27 passed), `tests/unit/test_experiment_metrics.py` (24 passed),
  `tests/unit/test_cli_dispatch.py` and
  `tests/integration/test_ingest_tracking.py` (50 passed, regression
  check) -- 361 passed total, run twice (once against the loaded
  rehearsal sample, once after clearing it).
- Not wired into any production path -- matches every sibling model
  family's own dormant-until-a-separate-promotion-decision posture. No
  champion/challenger comparison or promotion decision was made.

### Plan 04D -- base/out transition matrix + run expectancy (first package) -- 2026-08-19 (`mlb_test` only)

- Added `mlb_baseball/model/markov.py` and
  `mlb_baseball/sql/markov_transition_counts.sql`: estimates the classic
  24-state (8 base configurations x 3 outs) base/out Markov chain plus one
  absorbing `TERMINAL` state directly from `raw.retrosheet_event`, scoped
  to regular-season games via the same `raw.retrosheet_gameinfo` join
  every sibling retrosheet_event consumer uses -- plus the RE24-style
  run-expectancy table derived from it (`run_expectancy`, solving the
  absorbing-chain identity `(I-Q)@RE=r` via `numpy.linalg.solve`, no new
  dependency). Plan 04D's first deliverable ("Estimate base/out transition
  matrices and run expectancy by context... validate probabilities and
  conservation rules"); the simulator and calibration against held-out
  seasons are separate follow-up packages.
- **Correction to `docs/RESEARCH.md`, found before writing any code:**
  that doc claimed `core.play` has the data to build this directly.
  Checked directly against the live schema: `core.play` has `outs` but no
  runner-on-base columns at all -- no equivalent of `raw.retrosheet_event`'s
  `base1/2/3_run_id`/`bat_dest_id`/`run1/2/3_dest_id`. Built off
  `raw.retrosheet_event` instead (already ingested, no new source/schema
  change). See ADR-076.
- **No sequential per-game walk needed, confirmed not assumed:** every
  `raw.retrosheet_event` row already self-describes both its pre-play
  state and everything needed to derive its post-play state, so this is a
  single aggregate `GROUP BY` query, not a stateful per-game replay.
- **Destination-code mapping verified against real rows:** confirmed via
  a full `GROUP BY` scan that `bat_dest_id`/`run{N}_dest_id` values `5`
  and `6` occur in real data (26,080 + 345 rows) and represent
  error-driven/team-unearned scoring, not a distinct "special"
  destination -- `IN (4,5,6)` is treated as "reached home" throughout, not
  just `= 4`, which would have undercounted runs on those plays.
- **A real conservation rule beyond "probabilities sum to 1":**
  `_validate_row_conservation` rejects any row where
  `runs_scored + post_b1 + post_b2 + post_b3` exceeds
  `pre_b1 + pre_b2 + pre_b3 + 1` (existing runners plus the batter) --
  catches encoding bugs a pure probability-normalization check can't see.
  Also rejects outs decreasing and `post_outs > 3`.
- **Verified against real production-shaped data:** ran the raw SQL
  directly against real `mlb` (read-only, no write) for season 2019 --
  bases-loaded/0-outs shows a substantially higher one-step scoring rate
  than bases-empty/0-outs (585/680 vs. 1,787/46,017), the expected
  direction. `tests/integration/test_model_markov.py` seeds a hand-built
  multi-game fixture and asserts the resulting matrix matches
  hand-calculated probabilities exactly, including that playoff-game and
  wrong-season rows are correctly excluded.
- **Run expectancy checked against published RE24 tables, not just
  internal consistency:** ran `estimate_run_expectancy` against real
  `mlb` (read-only, season 2019). Every value is correctly monotonic
  (decreases as outs increase, increases as more bases are occupied) and
  closely matches widely-published modern-era RE24 values: bases
  empty/0 outs 0.542 (published ~0.48-0.56), bases loaded/0 outs 2.430
  (published ~2.28-2.42), bases empty/2 outs 0.115 (published
  ~0.10-0.12), bases loaded/2 outs 0.790 (published ~0.74-0.81) --
  strong end-to-end evidence the whole pipeline is correct, not just
  that it runs without crashing.
- `uv run ruff check .`/`uv run ruff format --check .` clean,
  `uv run mypy mlb_baseball/model/markov.py` clean.
  `tests/unit/test_markov_transitions.py` (10 passed, pure logic, no DB)
  and `tests/integration/test_model_markov.py` (3 passed, real Postgres) --
  both TDD, written and watched fail before implementation.
- **Found and fixed a real, pre-existing, unrelated test-pollution issue
  while verifying against `mlb_test`:** `tests/integration/test_audit_db.py`
  depends on `raw.retrosheet_gameinfo` carrying its full real column set,
  but several `test_model_*.py` files' own `_reset()` fixtures
  unconditionally `DROP TABLE`+recreate it with a minimal stub (this
  file's new fixture included) -- whichever runs last in a shared
  `mlb_test` session leaves the table too narrow for
  `test_audit_db.py`'s assumptions. Fixed by reloading the real schema
  from production `mlb` (read-only) into `mlb_test`; the underlying
  fragility (these fixtures fighting over one shared table's shape) is
  real and not fixed here -- tracked as issue #37.
- No persistence layer added -- `estimate_transition_matrix`/
  `estimate_run_expectancy` return in-memory results, no new migration or
  `meta`/`gold` table, matching every dormant Plan 04 research module's
  "not wired into production" posture.
