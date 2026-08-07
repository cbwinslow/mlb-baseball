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
