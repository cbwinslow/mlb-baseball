# Modeling and Simulation DOX

## Purpose

Own the current/legacy predictive-model, simulation, feature-enrichment, and
model-evaluation code under `mlb_baseball/model/` while the research database is
the active product focus.

This subtree is intentionally constrained: new Engine/package proliferation is
frozen unless the work directly supports an accepted research-database/statistics
contract or an explicitly reopened modeling plan.

## Ownership

- model families and training/inference implementations;
- evaluation/calibration/promotion-review logic;
- simulation and Markov components;
- legacy/current feature enrichments that have not yet moved to neutral stats or
  SQLMesh ownership;
- model-specific health checks and artifacts.

Pure reusable baseball statistics should move toward a neutral stats/domain layer
when that boundary is introduced; `model/` should not remain the permanent owner
of general sabermetric truth.

## Local Contracts

### Point-in-time correctness

- Training features, validation features, and inference inputs must contain only
  information knowable at the declared cutoff.
- Chronological/rolling-origin validation is required for time-dependent targets;
  never use random folds as the primary evidence for game forecasting.
- The final forward/test period must not be used to select features or tune
  decisions.
- Stacked/ensemble inputs must be out-of-fold for training rows.
- Snapshot/version/cutoff identity must be reproducible enough to explain every
  prediction used in evaluation.

### Evaluation

For probability predictions, prioritize:

- log loss;
- Brier score/decomposition;
- calibration/reliability;
- sharpness/coverage;
- uncertainty and sample size;
- matched-sample comparison to baselines and, later, permitted market prices.

Accuracy alone is not sufficient evidence. Suspiciously strong game-winner
results trigger a documented leakage review; they are not automatically proof of
leakage or automatic promotion/rejection.

### Promotion

Promotion is a recorded review (promote / hold / return-with-gaps), not an
automatic threshold. Preserve negative results and failed candidates so they are
not repeatedly rediscovered.

### Modeling order

Transparent baselines come before complexity. Prefer empirical/log5/Elo/GLM-style
or other interpretable baselines before claiming value from boosting, neural,
sequence, or ensemble methods. GPU/NN work is justified by measured benefit, not
hardware availability.

### Determinism and agents

LLMs/agents may research papers, propose features, review code, explain structured
results, or triage anomalies. They must not directly generate stored gold
statistics or unvalidated probability outputs as project truth.

## Work Guidance

Read `docs/RESEARCH.md`, relevant ADRs, the active product direction, and the exact
module/tests before changing modeling behavior.

Do not broaden `gold.game_feature` merely because a candidate feature exists.
Prefer stable narrow research relations and governed feature admission.

Keep pure computation separate from DB access. The Markov split between pure core
math and estimator/database access is the preferred direction; issue #111 tracks
remaining eager-import coupling. The detailed local contract is in
`markov/AGENTS.md` and applies whenever that subtree is touched.

When refactoring a legacy Engine module, classify it as one of:

- validated research statistic;
- model primitive;
- visualization/display metric;
- research prototype;
- superseded/archive.

Do not create another Engine package to avoid making that classification.

## Verification

Changes generally require relevant unit tests plus chronological integration/
evaluation tests. Formula changes also need hand fixtures/tie-outs.

Representative commands:

```bash
uv run pytest tests/unit -q
uv run pytest tests/integration -q
uv run ruff check mlb_baseball/model tests
uv run mypy mlb_baseball/model
```

For model performance claims, include the exact dataset/snapshot, seasons/folds,
baselines, matched sample, metrics, and uncertainty—not only a headline score.

## Child DOX Index

| Child | Scope |
| --- | --- |
| [markov/AGENTS.md](markov/AGENTS.md) | Pure base/out Markov math and DB-backed Retrosheet/Statcast estimators with strict PIT rules. |

Do not mechanically add children for every legacy Engine directory/module. Add a
child only when a stable conceptual boundary has distinct local contracts.
