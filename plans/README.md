# MLB execution plans

These plans convert `docs/PROJECT_REVIEW.md` and `AGENTS.md` into the execution
sequence for Antigravity/Gemini 3.6 Flash (Medium). Run one work package at a
time. Do not skip a gate because later work depends on the contracts established
earlier.

## Sequence

| Plan | Outcome | Depends on |
|---|---|---|
| [00](00-workspace-reconciliation.md) | clean, reviewed baseline | none |
| [01](01-correctness-rights-security.md) | trustworthy and safely scoped platform | 00 |
| [02](02-sql-transforms-and-ingestion.md) | named SQL, decomposed conformance, durable ingestion | 01 |
| [03](03-research-statistics-and-features.md) | governed research/statistics/feature factory | 02 |
| [04](04-modeling-simulation-and-experiments.md) | reproducible multi-target modeling program | 03 |
| [05](05-serving-astro-and-launch.md) | original public research/forecast product | 04 |

## Current status

| Plan | Status |
|---|---|
| 00 | Accepted / archived baseline |
| 01 | Active; 01F production cutover blocked pending R1–R6 remediation |
| 02 | SQLMesh foundation/candidate gate accepted; overall plan incomplete and deferred behind 01F |
| 03 | Blocked by 01F and remaining Plan 02 contracts |
| 04–05 | Queued |

## Delegation protocol

For each numbered work package, give Antigravity a self-contained prompt quoting
the relevant plan section and `AGENTS.md`. Use `accept-edits` only after the owner
authorizes implementation. Require it to preserve unrelated changes, use only the
existing `mlb_test_codex` test database, avoid production writes, and return changed
files, commands/results, limitations, and the next gate. It must not commit,
merge, delete worktrees, or begin the next package unless explicitly authorized.

GPT-5.6 Sol performs the gate review: inspect diffs, run proportional independent
verification, compare acceptance criteria, record decisions, then authorize the
next package. Failed ideas and rejected designs are documented rather than erased.

## Global success measures

- Clean-clone bootstrap, migration, conform, prediction, evaluation, and site
  data build are documented and reproducible.
- Every public result is traceable to permitted sources, feature snapshot, model
  artifact, prediction cutoff, and generated time.
- No SQL business formula has untracked duplicate implementations.
- All evaluation is point-in-time correct, matched-sample, calibrated, and honest
  about uncertainty and missing coverage.
- The site works at $0/month with optional monetization disabled.

## Immediate contract gates

Before broadening models or public serving, resolve these cross-plan contracts:

1. **Prediction identity:** `mlb_game_pk` is not globally unique for real
   suspended/resumed games. Define a durable game-instance/feature identity and
   carry it through features, predictions, outcomes, evaluation, and serving.
2. **Workflow serialization:** enforce—not merely document—the dependency chain
   `ingest → conform → features → predict`; per-source locks alone do not prevent
   conflicting cross-stage runs.
3. **Feature reuse:** retain backward-compatible `mlb predict` behavior, but add
   a verified reuse path so an independently health-checked feature build is not
   silently rebuilt immediately before prediction.
4. **Reproducibility honesty:** current feature snapshots are fingerprints of an
   in-place table, not immutable row storage. Do not claim full replayability
   until Plan 03 supplies immutable target/cutoff-specific snapshots.
5. **Public safety:** no Astro/public result may use a source merely because it
   was locally ingested; serving must enforce lineage and `public_safe` rights.
