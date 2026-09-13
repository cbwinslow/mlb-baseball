# Modeling and research-model DOX

## Purpose

This subtree contains the current modeling/statistical research implementations, experiments, evaluation helpers, and many historical metric/engine modules. It is a large legacy/research surface and is **not** a license to keep adding new modules indefinitely.

**Two products** (`openspec/project.md` — "Who it's for"): the walk-forward backtest harness, the point-in-time feature store, the Markov/sim engine, and **one** reference baseline model (Elo v2) are part of the public `mlb-research` toolkit and **ship**. Tuned model weights and configs, backtest results for any non-baseline model, and the model ladder above the baseline are the internal Engine and **stay private**. Apply `project.md`'s one-sentence ship/internal test — do not re-derive it here.

The Engine (Phase B of the ladder) is **SPECULATIVE and gated**: it does not start until Phase A's feature store is stable and versioned, and only after a re-evaluation says go. Until then, model work is limited to what Phase A needs.

## Ownership

- Existing model/statistical implementations that have not yet been moved to a neutral `stats/` package.
- Point-in-time model/evaluation helpers and backtesting logic. The pure
  evaluation math (fold construction, metrics, calibration, aggregation) has
  **one implementation, `mlb_research.backtest`** (feature-store-v1 slice 2)
  -- `experiment.py`'s `run()` is that harness's `mlb_baseball`-side adapter:
  it builds the evaluation `DataFrame` from `meta.experiment_snapshot`,
  wraps the sklearn/xgboost estimator zoo and the `elo`/`log5`/`home_rate`
  families as `fit_fn`/`predict_fn` factories, calls
  `mlb_research.backtest.run_backtest`, and writes the result to
  `meta.experiment*` exactly as before. Do not reimplement fold/metric math
  locally; extend `mlb_research.backtest` and re-export.
- The reference baseline model itself now ships as `mlb_research.elo`
  (Elo v2: v1's math unchanged, plus a fading preseason prior and a
  starter-quality adjustment, feature-store-v1-baseline) with its model
  card (`build_model_card`/`render_model_card`), evaluated through
  `mlb_research.backtest`. `model/elo.py` in this subtree (v1, Postgres,
  writes `gold.game_feature.home_elo`/`away_elo`) is a **separate**
  implementation feeding production feature engineering, not this shipped
  baseline -- do not conflate the two, and do not add Elo math to a third
  place.
- Research prototypes that are still actively validated or used.
- Compatibility exports currently exposed from `model/__init__.py`.

## Local Contracts

- Do not add a new model/metric module merely because a formula exists. First classify it as: validated research statistic, predictive feature primitive, visualization metric, prototype, or superseded/archive candidate.
- Pure baseball/statistical math should migrate toward a neutral lightweight `mlb_baseball/stats/` boundary when doing so reduces coupling; reporting/CLI/DB layers should depend on stats, not the reverse.
- `model/__init__.py` currently acts as a broad facade and eagerly imports substantial dependencies. Preserve compatibility while reducing eager/heavy imports incrementally rather than breaking all callers at once.
- Every predictive evaluation must be chronological / point-in-time correct. Random train/test splitting is not acceptable for time-dependent MLB forecasting claims.
- Never select features or hyperparameters on the final test/forward period.
- Base predictions used in ensembles/stacking must be out-of-fold for the training examples that consume them.
- Report probability quality (log loss, Brier score/decomposition, calibration, sharpness/coverage/uncertainty as appropriate), not accuracy alone.
- A model not beating baselines is not automatically deleted or promoted; promotion is a recorded review based on evidence, stability, use case, and leakage checks.
- Betting/value claims require permitted timestamped market observations, vig-aware comparison, and matching forecast cutoff semantics. Model probability, market probability, fair price, EV, and recommendation are separate concepts.
- Formula implementations require authoritative citation/rationale, bounds/null behavior, deterministic hand fixtures, and tie-out/cross-reference validation where the project doctrine requires it.
- Do not silently turn missing measurements into zeros.
- GPU/JIT/parallel acceleration must follow profiling/benchmark evidence; correctness/reproducibility comes first.

## Consolidation Rule (until Phase B opens)

Phase B item 1 — Engine triage into a `meta.metric` registry — is a **sanctioned lane**, but it is gated on Phase A (`openspec/project.md`, phased ladder). Until Phase B opens:

- favor validating, classifying, consolidating, or extracting existing assets;
- do not expand the "Engine"/metric catalog except for a directly required Phase A research primitive;
- new reusable descriptive statistics should target the planned neutral `stats/` package/registry instead of deepening this legacy namespace;
- preserve useful negative results and provenance rather than rerunning the same failed idea.

When Phase B opens, the triage runs against this whole namespace at once — that is expected, not a violation of the "no mass rewrite" rule; classification is not rewriting.

## Progressive Context

Before editing a specific modeling module:

1. Read root `AGENTS.md`, `mlb_baseball/AGENTS.md`, and this file.
2. Read the module and nearest tests/research references.
3. If the module has a future `<module>.dox.md` sidecar, read it for exact formula/data/PIT contracts.
4. Load model/research runbooks or skills only for the task being performed.

Do not create `.dox.md` sidecars for every historical Engine module in one mechanical sweep. Start with load-bearing evaluation/PIT modules and modules being actively promoted or decomposed. (The Phase B `meta.metric` triage classifies modules into a registry table — that is not the same as writing a sidecar per module.)

## Work Guidance

- Baselines first; complexity must earn its cost.
- Keep dataset/feature/model versions and experiment configuration reproducible.
- Separate descriptive statistic computation from predictive feature construction when their semantics differ.
- Make availability timestamps/cutoffs explicit in datasets and tests.
- Prefer immutable typed configuration/artifact metadata for reproducible experiments.
- Keep training/inference deterministic where feasible and record randomness/seeds when not.

## Verification

Depending on the change:

- pure unit tests / hand-calculated fixtures;
- chronological holdout or rolling-origin tests;
- real-Postgres integration tests for stored experiment/evaluation artifacts;
- calibration/baseline comparisons for modeling changes;
- citation/tie-out checks for formulas;
- lint/type checks.

Do not describe an experiment as validated unless the actual held-out protocol was run.

## Child DOX Index

No child directory DOX yet. Create domain children only during a deliberate reorganization (for example `stats/`, `forecast/`, `evaluation/`) when those boundaries become real and stable.
