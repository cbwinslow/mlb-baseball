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

**Status:** Implementation exists but production cutover is BLOCKED pending remediation. Production `mlb` has not been touched and no production cutover is authorized.

**Evidence correction (2026-08-10):** The prior premise that a suspended or
resumed game creates two valid MLB game instances sharing `game_pk` is false.
Official MLB documentation and baseballr define it as the unique game ID;
production schedule duplicates are source-history observations.  The earlier
`game_instance_key` migration remains a compatibility artifact pending a
tested, forward-only correction. See `docs/GAME_INSTANCE_IDENTITY.md`.

**Cutover Blockers:**
- The existing 0034–0037 `game_instance_key` cutover was built on the now-rejected
  premise that one MLB game can require two identities. It needs a tested,
  forward-only compatibility correction; do not rewrite applied migration files.
- `core`/`gold` are empty in production, so canonical conformance and pitch/play
  join coverage have not yet been proven at production scale.
- Statcast's raw `game_pk` coverage is complete, but the earlier sparse
  Statcast-to-core join must be remeasured after canonical conformance with its
  retained source key and every remaining category documented.
- A production conformance rebuild remains owner-authorized work only.

#### 01F remediation sequence

Production `mlb` remains out of scope. Any later database verification uses only
the existing `mlb_test` database.

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
