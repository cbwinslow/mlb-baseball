# Plan 01 — Correctness, data rights, and security

## Objective

Make the platform trustworthy enough that later feature/model breadth does not
scale errors, leakage, rights violations, or credential exposure.

## Work packages

### 01A — Core linkage and health gates

Rebuild and verify `game_pk`, team/player identity, game-number normalization,
and pitch/play linkage by season. Add coverage, ambiguity, duplicate-key, and
referential gates with explicit thresholds and drill-down queries. Optimize
`mlb doctor` so checks stream progress and expensive checks are bounded.

### 01B — Forecast correctness

Finalize log5-v2 boundary behavior; evaluate one pregame snapshot per game at
`open`, `24h`, `6h`, and `close`; compare exact matched samples; add game-clustered
intervals, calibration outputs, and coverage. Preserve invalid historical versions
as labeled history. Freeze a final holdout and define rolling-origin folds.

### 01C — Immutable provenance

Create model, model-run, artifact, feature-snapshot, evaluation, and prediction
identity. Content-address artifacts; never overwrite a version in place. Record
git SHA, parameters, training/data cutoffs, source snapshot, feature version,
metrics, status, and errors. Champion promotion requires practical improvement,
not a microscopic point-estimate win.

### 01D — Enforced source profiles

Build a source-rights matrix with evidence, permitted uses, attribution,
redistribution, ML, generated-content, and commercial flags. Implement
`public_safe`, `licensed_full`, and `local_research` allowlists across ingestion,
features, training, serving, downloads, and content. Remove restricted inputs
from public artifacts; do not assume noncommercial use cures restrictive terms.

### 01E — Least privilege

Define owner/migration, ingestion, transform, and read-only serving roles; restrict
host/network rules, require appropriate transport security, set secret files to
owner-only, rotate exposed credentials if necessary, and prevent Astro from ever
querying `raw`. Supply reversible DBA instructions; do not mutate host security
or production roles without explicit owner approval.

### 01F — Operational identity and serialization

Establish a correct, durable game identity and prevent fanout: one canonical
MLB game per provider `mlb_game_pk`, with postponed/suspended/resumed schedule
history retained in `raw`, and Retrosheet's native ID retained where no safe
crosswalk exists. Carry that contract through outcome backfill, evaluation,
market matching, and eventual serving objects. Add a workflow-level
lock/dependency gate so `ingest → conform → features → predict` cannot overlap
in an inconsistent order; retain per-source locks for connector serialization.
Make migration execution serializable too. Clearly separate read-only
diagnostics from owner-authorized stale-run repair.

**Status:** The canonical identity correction and a production core rebuild were
completed under prior owner authorization on 2026-08-12. **Superseded
2026-08-18**: migrations 0040-0056 (including the `core.game.game_pk` unique
index) and a full production `core`/`gold` rebuild were owner-authorized and
executed against production `mlb` — see `PROGRESS.md` "Plan 01F production
cutover executed" for evidence. `gold.game_feature`/`gold.player_season`/
`gold.team_season`/`gold.division_standing` are populated in production;
`mlb predict` has run. This closes R1-R4 of the remediation sequence below in
production, not just `mlb_test`. **R5 evidence added 2026-08-26** (see the R5
entry below and `docs/DECISIONS.md` ADR-255) — real coverage gaps closed and
one real bug fixed in `mlb_test`, but not yet Sol-reviewed or applied to
production; treat R5 as pending review, not closed. R6
(documentation/final verification) remains open and not started.

**Evidence correction (2026-08-10):** The prior premise that a suspended or
resumed game creates two valid MLB game instances sharing `game_pk` is false.
Official MLB documentation and baseballr define it as the unique game ID;
production schedule duplicates are source-history observations.  The earlier
`game_instance_key` migration remains a compatibility artifact pending a
tested, forward-only correction. See `docs/GAME_INSTANCE_IDENTITY.md`.

**Cutover Blockers (resolved 2026-08-18 — kept here for history, see the
Status note above):**
- The existing 0034–0037 `game_instance_key` cutover was built on the now-rejected
  premise that one MLB game can require two identities. It needs a tested,
  forward-only compatibility correction; do not rewrite applied migration files.
  Resolved by migration `0044_canonical_mlb_game_identity.sql`, applied to
  production 2026-08-18.
- ~~`gold` remains empty in production.~~ Resolved 2026-08-18: `gold.game_feature`
  (217,186 rows), `gold.player_season`, `gold.team_season`,
  `gold.division_standing` are now populated in production; `mlb predict` has
  run.
- Statcast's raw `game_pk` coverage is complete, but the earlier sparse
  Statcast-to-core join must be remeasured after canonical conformance with its
  retained source key and every remaining category documented.
- ~~A production conformance rebuild remains owner-authorized work only.~~
  Executed 2026-08-18, owner-authorized — see `PROGRESS.md`.

#### 01F remediation sequence

Production `mlb` was out of scope through R1-R4's `mlb_test`-only rehearsal
evidence below; the production cutover itself (owner-authorized, executed
2026-08-18) is recorded in `PROGRESS.md` "Plan 01F production cutover
executed," not in this historical rehearsal-evidence section. R5/R6 evidence
below still applies only to `mlb_test` until separately executed against
production.

1. **01F-R1 — read-only evidence:** run the bounded game audit and the opt-in
   Statcast scan. Gate: exact required-null, duplicate, orphan, schedule-history,
   and source-key coverage evidence with actionable samples.
2. **01F-R2 — canonical conformance:** prove in `mlb_test` that one populated
   `core.game.game_pk` maps to one canonical MLB game, while Retrosheet-only
   records retain their native key. Gate: doubleheader, postponed/resumed,
   ambiguity, rebuild, and payload-preservation coverage.
3. **01F-R3 — pitch/play classification:** retain the Statcast source game key
   when `core.pitch.game_id` is unresolved, measure every unresolved category by
   season, and only promote a deterministic mapping proven by fixtures. Gate:
   source-key, no-row-loss, coverage, and rerun coverage.
4. **01F-R4 — compatibility correction:** replace or repurpose the legacy
   `game_instance_key` consumer path through a forward-only migration after
   exact historical mapping evidence. Gate: immutable prediction preservation,
   no-fanout joins, interruption/retry, and competing-migration-lock coverage.
5. **01F-R5 — consumer/workflow integrity:** reverify prediction-boundary
   consumers and incompatible workflow overlap rejection. Gate: prediction-boundary
   consumer validation and workflow overlap rejection coverage.
6. **01F-R6 — documentation/final verification:** align contracts, runbooks,
   API, and audit output; run proportional sequential verification before a Sol
   review. No production cutover is authorized by completion of this plan.

**R2/R3 rehearsal evidence (2026-08-10):**
`test_multi_source_conformance_rehearsal_ties_out_across_grains` builds a
small multi-era raw fixture in `mlb_test`, runs conformance twice, verifies
exact game/play/pitch and raw-count snapshots, and runs the bounded audit. It
covers Retrosheet-only history, a doubleheader, postponed/final schedule
history, a current MLB-only final, excluded scheduled/live rows, both play
sources, and resolved/unresolved Statcast pitches. See
[`CONFORMANCE_REHEARSAL.md`](../docs/CONFORMANCE_REHEARSAL.md). This is a
test-database gate, not authorization to modify production.

**Production-shaped rehearsal evidence (2026-08-11):** A bounded copy from
production opened the source transaction read-only and wrote only `mlb_test`.
It tied out 40 matched Retrosheet games (2008/2015/2024/2025), 3,167 Retrosheet plays,
753 MLB plays, and 14,154 Statcast pitches with zero unresolved sampled pitch or
play game links. It produced 2,303 canonical games, 3,920 plays, and 14,154
pitches; a second conformance run had identical raw/core snapshots. `core.game`
had zero duplicate populated MLB keys and left only `MLB824912` (2026-06-17,
retained suspended/resumed schedule history) without a key. The initially reported `raw.retrosheet_team`
2021 horizon is an official Retrosheet source limit, not a failed download:
`core` treats the file's shared active-team maximum as open-ended. The rehearsal
now mirrors that rule and includes 2024–25 Retrosheet games; `raw.mlb_team_history`
supplies authoritative numeric IDs for modern name changes. This removes the
reference-horizon blocker for the test gate, but does not authorize production
conformance. See
[`CONFORMANCE_REHEARSAL.md`](../docs/CONFORMANCE_REHEARSAL.md).

**R6 handoff evidence (2026-08-11):** `mlb preflight --with-conform` now
prints the safe operational order: migration, raw landing, doctor/inventory,
conform, then game and exact Statcast audits. `docs/BOOTSTRAP_RUNBOOK.md`
documents the clean-clone path, simple `.env`/optional `mlb.toml` configuration,
retry/diagnostic commands, and an AI-agent checklist. `mlb inventory` defaults
to a readable parent-only estimate view; `--exact` and `--partitions` retain
the full-detail inspection path. The database audit detects exact duplicate
physical indexes. Migration 0043 removes only duplicate non-unique raw indexes
in a future owner-authorized migration run; production remains unchanged.

**R4 compatibility evidence (2026-08-11):** Forward-only migration
`0044_canonical_mlb_game_identity.sql` corrects the earlier schedule-instance
assumption without discarding historical provenance. MLB feature/prediction
compatibility keys are now `mlb:<game_pk>`; Retrosheet keys remain native; old
schedule-shaped registry records are retained as `legacy`. The migration stops
before changing anything when duplicate populated feature MLB keys or duplicate
prediction MLB-key/model/timestamp records exist. `gold.prediction` now has its
canonical primary key `(mlb_game_pk, model_version, generated_at)` and
`gold.game_feature` has a partial unique populated MLB-key index. The focused
migration/evaluation/feature/prediction suite passed 135 tests in `mlb_test`.
Production remains read-only and requires separate owner approval.

**R5 consumer/workflow integrity evidence (2026-08-26):** Reverified both
halves of R5 against real `mlb_test`, not by assumption.

*Workflow overlap rejection:* the existing
`test_workflow_lock_serializes_connectors_and_derived_stages` only proved a
shared (connector) lock and an exclusive (derived-stage) lock reject each
other — never that two *exclusive* stages reject each other. Added
`test_workflow_lock_serializes_two_exclusive_derived_stages`
(`tests/integration/test_ingest_tracking.py`), using conform's and
features' real, different `SOURCE` values (`"core"`/`"model"`) specifically
so the per-source advisory lock cannot be what's serializing them — only
the shared `mlb-workflow:raw-core-model` lock can. Also re-checked every
real CLI-reachable `track_run()` call site (`conform.py`, and
`model/__init__.py`'s `run_features()`/`run()`/`train()`/`evaluate()`,
which back `mlb conform`/`mlb features`/`mlb predict`/`mlb train`/
`mlb evaluate`): all five already pass `workflow="exclusive"`. No gap found
there, no code change needed.

*Prediction-boundary consumer validation:* `mlb_baseball/model/evaluation.py`
and `mlb_baseball/model/market.py` already have solid, direct test coverage
of the acceptance gate's named properties (schedule history counted as one
game, post-start predictions excluded, MLB-keyed vs. Retrosheet-native-keyed
predictions kept distinct) — confirmed by reading `tests/integration/
test_model_evaluation.py` and `tests/integration/test_model_market.py`, not
duplicated. Found a real, previously-unfixed bug in two `serve.*` views:
`serve.daily_betting_grid` and `serve.prediction_market_alpha` both joined
`gold.prediction` directly on `(game_instance_key, model_version)` without
selecting the latest snapshot, fanning one real game out into one row per
historical prediction snapshot — the exact fan-out pattern migration 0082
already fixed for `serve.sgp_matchup_grid`/`serve.pitcher_arsenal`, which
just never reached these two. Fixed forward-only in
`migrations/0083_correct_remaining_serve_prediction_fanout.sql`; confirmed
by hand that reverting it reproduces 2 rows for 1 game with two prediction
snapshots, via the new
`tests/integration/test_serve.py::test_serve_daily_betting_grid_uses_latest_prediction_snapshot_only`
and `::test_serve_prediction_market_alpha_uses_latest_prediction_snapshot_only`.
A second, related but distinct bug in the same view
(`serve.prediction_market_alpha` also fans out on non-moneyline
`core.market` rows for Polymarket) was found but not fixed here — fixing it
safely needs either a `to_regclass`-gated conditional view or a
`core.market`-level market-type column from `conform.py`, both real,
separate design work; filed as
[issue #79](https://github.com/cbwinslow/mlb-baseball/issues/79). See
`docs/DECISIONS.md` ADR-255 for full detail on both parts.

`uv run pytest tests/integration/test_ingest_tracking.py
tests/integration/test_serve.py -v` — 16 tests, all passing, against real
`mlb_test`. Production `mlb` untouched throughout — this is a
`mlb_test`-verified, forward-only migration plus test change, same as every
prior R1-R4 rehearsal entry above. R6 (documentation/final verification)
remains open, not started by this change.

## Acceptance gate

- Modern-season linkage meets recorded targets and ambiguous identities remain
  NULL rather than guessed.
- Evaluation cannot count snapshots as games or include post-start predictions.
- A prediction can be traced end-to-end and artifacts are immutable.
- One prediction/evaluation row maps to exactly one declared MLB game key or
  Retrosheet-native game key; schedule history never creates a second game.
- Cross-stage overlap tests prove an incompatible run is rejected before it can
  truncate or consume an unstable upstream relation.
- Automated tests prove forbidden sources cannot enter `public_safe` outputs.
- Role tests prove the serving principal can read only approved serving objects.
