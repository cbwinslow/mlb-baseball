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

Replace the overloaded `mlb_game_pk` prediction identity with a durable
game-instance/feature identity that handles scheduled, completed, and
suspended/resumed games without fanout. Carry that identity through outcome
backfill, evaluation, market matching, and eventual serving objects. Add a
workflow-level lock/dependency gate so `ingest → conform → features → predict`
cannot overlap in an inconsistent order; retain per-source locks for connector
serialization. Make migration execution serializable too. Clearly separate
read-only diagnostics from owner-authorized stale-run repair.

**Status:** Implementation exists but production cutover is BLOCKED pending remediation. Production `mlb` has not been touched and no production cutover is authorized.

**Cutover Blockers:**
- Registry `meta.game_instance` is created in 0036 after 0035 fails, while backfill requires it.
- Prediction `game_instance_key` lacks explicit NOT NULL cutover gate.
- Interrupted `CREATE INDEX CONCURRENTLY` can leave invalid index and `IF NOT EXISTS` is not a safe retry.
- Legacy prediction mapping through current feature rows is not historically unambiguous.
- Deterministic batch ordering must use full old primary key.
- `mlb doctor`, runbook, contracts, and public API need alignment and explicit read-only validation checks.

#### 01F remediation sequence

Production `mlb` remains out of scope. Any later database verification uses only
the existing `mlb_test` database.

1. **01F-R1 — schema availability:** create nullable identity columns and the
   registry before the blocking cutover migration. Gate: repeatable schema-prep
   test with no backfill or key replacement.
2. **01F-R2 — deterministic historical backfill:** use the registry as authority;
   canonicalize only defensible one-to-one matches and otherwise preserve
   deterministic legacy keys. Gate: resume, ambiguity, rebuild, and payload-preservation coverage.
3. **01F-R3 — read-only validation:** add NULL, duplicate, registry-coverage,
   orphan, invalid-index, and incomplete-state diagnostics. Gate: no mutation and
   actionable premature-cutover failure.
4. **01F-R4 — concurrent cutover/retry state machine:** require NOT NULL on both
   identities and recover every partial concurrent-index/ledger state. Gate: real-Postgres
   interruption/retry and competing-migration-lock coverage.
5. **01F-R5 — consumer/workflow integrity:** reverify all prediction-boundary
   consumers and incompatible workflow overlap rejection. Gate: prediction-boundary consumer validation and workflow overlap rejection coverage.
6. **01F-R6 — documentation/final verification:** align contracts/runbooks/API and run
   proportional sequential verification before a Sol review. Gate: contract/runbook/API alignment, clean test pass, and Sol review signoff; no production cutover is authorized by completion of this plan.

## Acceptance gate

- Modern-season linkage meets recorded targets and ambiguous identities remain
  NULL rather than guessed.
- Evaluation cannot count snapshots as games or include post-start predictions.
- A prediction can be traced end-to-end and artifacts are immutable.
- One prediction/evaluation row maps to exactly one declared game instance,
  including documented suspended/resumed-game handling.
- Cross-stage overlap tests prove an incompatible run is rejected before it can
  truncate or consume an unstable upstream relation.
- Automated tests prove forbidden sources cannot enter `public_safe` outputs.
- Role tests prove the serving principal can read only approved serving objects.
