# ML modeling harness: target-agnostic framework, feature selection, multi-technique design

**Status:** Design spec, not yet an implementation plan. Written via `superpowers:brainstorming`
on 2026-08-14 with the project owner. Extends Plan 04 (`plans/04-modeling-simulation-and-experiments.md`)
work packages 04A/04B/04C/04E/04F; does not replace or reorder them.

## Objective

The experiment lab (`mlb_baseball/model/experiment.py`, migrations 0047-0049) currently answers
exactly one question: can a declared model predict `home_win` from `game_base_v1`? The target is a
hardcoded Python constant and a hardcoded SQL `CHECK` constraint. This spec generalizes that lab so
it can hold more than one target — starting with `run_differential` — while keeping every existing
non-negotiable contract (chronological folds, immutable snapshots, transparent baselines before
complex models, strict promotion) exactly as strict as it is today. It also designs how feature
selection, multi-technique comparison, and higher-variance techniques (ensembles, Markov-derived
features, neural interaction models) plug into that same harness without weakening those contracts.

## Relationship to `docs/NORTH_STAR.md`

Phase 2's stated current priority is **"reproducible feature/prediction contracts before model
breadth."** This spec is written to satisfy that ordering: section 1 (target-agnostic framework) is
a contracts change — it makes the harness capable of holding a second target correctly, the same way
`docs/TABLE_CONTRACTS.md` and the immutable-snapshot work already did for the first one. Sections
2-6 are breadth, and are explicitly sequenced *after* section 1, gated by the promotion bar in
`plans/04-modeling-simulation-and-experiments.md`'s acceptance gate, not built in parallel with it.

## Implementation sequencing

This spec is broader than one implementation plan. Sections 1-2 (target-agnostic framework +
`run_differential` baselines/models/metrics) are the concrete, immediately buildable slice — the
next `superpowers:writing-plans` pass should scope from those two sections alone, in `mlb_test`
only, under the same bounded-rehearsal posture as the existing `home_win` experiment lab. Sections
3 (feature selection), 5 (ensembles), and 7 (interoperability) are designed now so their integration
points are already decided, but are separate, later-gated plans of their own. Section 4 (Markov-
derived features) is blocked on Plan 04D existing first and is not actionable yet. Section 6 (neural
interaction models) is deliberately sequenced last, after sections 1-3 give it something real to be
measured against.

## Non-goals for this spec (deferred, tracked, not abandoned)

Nothing below is ruled out. Some items are sequenced later in this same design (ensembles, Markov
features, neural interaction models — see sections 5/4/6). A few are genuinely outside this spec's
scope and tracked as separate follow-up tasks instead:

- Matching/exceeding baseball.computer's researcher-facing access (web query engine, Python/R,
  Jupyter/Colab notebooks) — a Phase 3 (Astro site) / interoperability project of its own.
- A general code-quality/DevOps reinforcement pass, PostgreSQL extension/index/data-type audit and
  benchmarking, a CLAUDE.md preference update, `.claude` folder commit, and a secrets-scanning
  pre-commit hook — all owner-requested in the same session, explicitly deferred until after this
  spec, tracked as separate tasks.

## 1. Target-agnostic experiment framework

**Current state (verified against source, not assumed):**

- `mlb_baseball/model/experiment.py:38` hardcodes `TARGET = "home_win"`.
- `mlb_baseball/model/experiment.py:631-632`: `run()` raises `ExperimentError` if
  `config.target != TARGET` — a second target cannot even reach the database today.
- `migrations/0047_experiment_lab.sql` hardcodes `CHECK (target = 'home_win')` on both
  `meta.experiment_snapshot` and `meta.experiment`.
- `model_family` has no SQL-level constraint — only a Python tuple
  (`_ALLOWED_MODEL_FAMILIES` / `MODEL_FAMILIES`) — so adding new estimators is already the
  intended extension point; only the target dimension needs new plumbing.
- `SnapshotRow` (`experiment.py:93-105`) already carries `home_score`/`away_score`. A
  `run_differential` target needs **no new snapshot columns** — only a new way to read the label
  out of a row that already has what it needs.

**Design:**

- Add `meta.experiment_target` (migration): `name text primary key`, `task_type text not null check
  (task_type in ('classification', 'regression'))`, `description text not null`. Seed it with two
  rows: `home_win` (classification), `run_differential` (regression). Replace both hardcoded `CHECK
  (target = 'home_win')` constraints with a foreign key to `meta.experiment_target(name)`. This
  keeps the same fail-closed posture — an unregistered target still cannot be written — but adding a
  third target later is a data row plus a code change, not a schema migration plus a code change.
- Add a `TargetSpec` frozen dataclass in `experiment.py`: `name: str`, `task_type: Literal["classification",
  "regression"]`, `label(row: SnapshotRow) -> float` (extraction function — `home_win` returns
  `float(row.home_win)`; `run_differential` returns `float(row.home_score - row.away_score)`),
  `metric_fn: Callable[[np.ndarray, np.ndarray, int], dict[str, Any]]`, `valid_model_families:
  tuple[str, ...]`. A small `TARGET_REGISTRY: dict[str, TargetSpec]` replaces the single `TARGET`
  constant; `ExperimentConfig.target` continues to be a plain string, validated against the registry
  at both the Python layer (fail fast, clear message) and the database layer (the new FK, defense in
  depth against a config bypass).
- `_matrix`/`_labels` become target-aware: `_labels` calls `spec.label(row)` instead of hardcoding
  `int(row.home_win)`. The existing `_probabilities`/`_calibration`/`_metrics` functions are
  classification-specific and are *not* generalized in place — see below.
- `_metrics` dispatches on `task_type`: existing log-loss/Brier/calibration path stays exactly as-is
  for `classification`; a new regression path (section 2) is added alongside it, not merged into it.
  Two clean functions are preferable here to one function with branching that makes the existing,
  already-reviewed classification path harder to read.
- `experiment compare` (CLI) generalizes to report whichever metric set the target's `task_type`
  produced — it already reads whatever `_metrics` wrote per fold, so this is close to free.

**Why not a fully generic "any target, any label shape" abstraction:** two task types
(classification, regression) is the real, current need — Plan 04B's target ladder lists ordinal/
distributional targets too (totals, run line) eventually, but building for those now would be the
kind of speculative abstraction CLAUDE.md's "Code quality" section warns against. `TargetSpec` is
deliberately just wide enough for two concrete instances that exist today.

## 2. First new target: `run_differential`

**Task type:** regression. **Label:** `home_score - away_score` (already available, no leakage risk
different from `home_win` — both are resolved at the same game-completion cutoff).

**Baselines, weakest to strongest, matching Plan 04B's "empirical, league-rate ... before complex
models" mandate — every one of these must be stood up and scored before any ML regressor is judged:**

1. **Zero baseline** — predict `0` (average team is average) — the run-differential analog of
   "predict 50%" for classification. Establishes the noise floor.
2. **Season-to-date average run differential** — `home_run_diff_avg - away_run_diff_avg`, both
   already-available `gold.game_feature` season-to-date aggregates (`home_runs_for -
   home_runs_allowed`, entering-value, already point-in-time-safe by construction since they're the
   same columns Pythagenpat and the run-environment feature family already read).
3. **Pythagenpat-derived expected differential** — already implemented and cited
   (`docs/RESEARCH.md` "Pythagorean expectation" section, David Smyth's adaptive exponent). Convert
   each team's Pythagenpat win% into an expected-runs framing consistent with its season run
   environment. This is a domain-informed baseline, the regression-target equivalent of Log5 for
   `home_win` — cheap, explainable, already sourced.

**ML regressors, mirroring the existing classification lineup so techniques are compared like-for-
like:** Ridge regression (regularized-GLM analog of the existing logistic-regression adapter),
HistGradientBoostingRegressor, XGBRegressor. Same estimator-adapter contract as classification: each
returns a real-valued prediction, uses the shared snapshot/fold/artifact plumbing, no
model-specific training script (`docs/EXPERIMENT_RUNBOOK.md` "Add a model" rule, unchanged).

**Metrics:** MAE and RMSE are primary (proper, easy to explain — this project's log-loss/Brier
posture is "proper scoring rules over accuracy," and MAE/RMSE are the regression equivalent of that
same philosophy, not a downgrade to a less rigorous standard). A residual-calibration check is the
regression analog of the existing probability-calibration bins: bin games by predicted differential,
report mean residual per bin — a well-calibrated model should have near-zero mean residual in every
bin, not just low overall error (a model that's great on blowouts and bad on close games can still
have a deceptively good aggregate MAE).

**Why regression is harder here, and how that's addressed (owner's own observation, confirmed by
the design):** run differential has much higher game-to-game variance than a binary win/loss outcome
— a similar signal-to-noise problem is why the reviewed literature (`docs/RESEARCH.md` ML section)
shows win-probability models clustering at a real, defensible 55-58% accuracy. The mitigation isn't
a fancier regressor — it's stronger *inputs*: section 4 (Markov-derived run expectancy) is
specifically sequenced right after this section because run-differential is exactly where an
engineered, domain-grounded feature has the best chance of moving the needle, more so than for
`home_win`, which already has strong baselines (Log5 at 97.9% efficiency ratio per the SABR
citation already in `docs/RESEARCH.md`).

## 3. Feature selection: three methods, scored for agreement, not for a single winner

Confirmed against literature during this brainstorming session (see citations below): wrapper
methods (stepwise) generally outperform filter methods but cost far more compute; embedded methods
sit between on both axes. Different methods commonly select different subsets even at similar
performance — a known stability problem, not specific to this project. The design treats that as a
feature, not a nuisance: cross-method agreement becomes its own evidence signal, extending the
existing "stability across eras/seasons" language in `plans/04-modeling-simulation-and-experiments.md`
section 04E to "stability across methods" as well.

**Stage 1 — cheap filter (runs on the full candidate pool, per target):** permutation importance of
each candidate feature against a cheap baseline model (e.g. the regression's Ridge baseline or
classification's logistic baseline), compared to the importance of a shuffled-noise column injected
into the same fit. A feature whose importance doesn't clear the shuffled-noise column's importance is
dropped from further consideration. This is the step that keeps cost bounded as Plan 03's admission
queue lands more feature families — a real, current growth path (multiple queued families already
listed in `docs/FEATURE_ADMISSION_QUEUE.md`), not a hypothetical one.

**Stage 2 — embedded (runs on the same full pool, independently of stage 1):** tree-based feature
importance (from the HistGradientBoosting/XGBoost fits already being trained for the model-family
comparison — no extra training cost, just extra reporting) and, for regression, the Ridge
coefficient-shrinkage path. Produces a second, independent ranking.

**Stage 3 — forward-stepwise wrapper (runs only on the stage-1 survivor set):** add one feature at a
time; keep it only if the *nested* walk-forward score (train fold → validate fold, same chronological
discipline as the outer experiment folds, applied inside each outer training fold) improves beyond a
noise threshold (established the same way stage 1's threshold is — against a shuffled column, not an
arbitrary epsilon). This is the literal "stepwise algorithm" from the original ask, deliberately
scoped to run only on the smaller survivor set so its cost doesn't grow quadratically with the full
registry.

**Output:** a stability report per target — which features all three methods agree belong, which are
method-specific (flagged, not silently dropped — this project's culture keeps negative/ambiguous
results, per `docs/RESEARCH.md`'s stacking section), and whether agreement holds across the existing
chronological era/season folds too. This report is an artifact, versioned the same way experiment
results already are — reproducible from the snapshot ID and method configuration, per Plan 04's
acceptance gate.

## 4. Markov-chain-derived features (bridges to Plan 04D)

Research finding worth recording: published work combining Markov chains with neural nets does so by
feeding **Markov-derived transition/expectancy values into the neural net or regression as
engineered features**, not by building some hybrid Markov-neural architecture. That's not a new
pattern for this project — it's exactly what `docs/RESEARCH.md`'s "Model stacking / ensembling"
section already calls pattern (a), "outputs as features," which `gold.game_feature` already does
with Elo and Pythagenpat.

**Design (depends on 04D's base/out transition matrix existing first — not part of this spec's
implementation, just the integration point):** once 04D produces a run-expectancy value per team
context, it becomes one more candidate column in the feature-selection pool from section 3, entering
through the exact same point-in-time-safe, health-checked path every existing `gold.game_feature`
enrichment family already uses (`docs/TABLE_CONTRACTS.md`). No special-cased plumbing — the value the
harness assigns it (kept, method-specific, or dropped) is exactly the evidence-based answer to
whether it actually helps, for either target.

## 5. Ensembles and stacking — back in scope, same promotion bar as before

Not deferred. `plans/04-modeling-simulation-and-experiments.md` section 04F already specifies the
bar: combine only calibrated models using **strictly out-of-fold** base predictions, and reject
stacks whose gains are unstable, expensive, or leakage-caused. `docs/RESEARCH.md`'s own record of
`stack-v1` (ADR-058) is the concrete precedent this project already has: a real stacking attempt,
correctly evaluated, correctly rejected on real held-out data (0.7174 vs. 0.6932 log-loss, n=10) —
and that verdict was *not* discarded, it was published as a documented negative result with a
specific, evidence-based reason it might be revisited (more decided games, wider market coverage).
This spec keeps that exact discipline: once section 1's framework exists for both targets, and
section 2's regression baselines/models are real, a new stacking attempt is legitimate research —
scored the same way, subject to the same "beat the best single model on real held-out data or it's a
recorded negative result" rule, for both `home_win` and `run_differential` independently (a stack
that helps one target has no presumption of helping the other).

Also revisit **democratic/voting methods** (simple unweighted or performance-weighted averaging
across the model-family lineup) as the cheapest possible ensemble to test first — meaningfully
cheaper than a trained meta-learner, and worth ruling in or out before a full stacking model, per the
literature's own note that ensembling reduces variance by combining diverse model types.

## 6. Neural / automatic feature-interaction models — in scope, staged, highest scrutiny

Real, legitimate technique family (AutoInt, DeepFM-style architectures — self-attention or
factorization-machine layers that learn feature *interactions* automatically instead of requiring
them to be hand-specified as ratios/products). Explicitly already anticipated by
`plans/04-modeling-simulation-and-experiments.md` 04C ("neural/sequence/embedding models where
structure and data justify them") and 04E ("mathematically justified exploration").

**Why staged last, not ruled out:** these architectures were built and validated at CTR-prediction
scale (millions to billions of examples). This project's chronological folds train on, at most, a
handful of MLB seasons — tens of thousands of games. The literature reviewed during this session
found a concrete cautionary example directly in this domain: a widely-cited MLB paper claiming
93-94% game-outcome accuracy turned out (per its own methodology, read closely) to use
within-season random cross-validation instead of a walk-forward split — the exact leakage class
`docs/RESEARCH.md` already names as the reason "70%+ accuracy is a signal to go hunting for a bug,
not a result to celebrate." A model family with enough capacity to memorize thousands of feature
interactions is, if anything, the *most* likely of everything in this design to quietly find and
exploit a leak rather than a real signal. Staging it after sections 1-5 isn't a demotion of the
technique — it's making sure the walk-forward/baseline-beating harness that can actually catch that
failure mode exists and is proven (on cheaper, faster-to-train models) before pointing the most
capacity-heavy technique at it.

**Gate, identical to everything else in this design, not a stricter invented one:** same
chronological folds, same requirement to beat the transparent baselines from sections 2/3, same
2025-holdout/2026-forward-monitor discipline already in force for `home_win`.

## 7. Interoperability

- **Parquet export** of a snapshot's resolved rows, documented alongside the existing
  `mlb experiment snapshot` command — lets a researcher without Postgres access reproduce a fold
  directly in pandas/R, matching the accessibility baseline `baseball.computer` already sets with its
  Python/R examples (full parity with its web query engine and hosted notebooks is out of scope here,
  tracked separately).
- **Model-family adapters conform to the plain scikit-learn estimator interface**
  (`fit`/`predict`/`predict_proba` as applicable) — already true of the existing adapters; stated
  explicitly here as a constraint so a future contributor (or a researcher extending this themselves)
  can add a new estimator without touching harness internals.
- **Prefer portable artifact formats where the library supports one** — XGBoost's native
  (`.json`/`.ubj`) format over a Python pickle where practical, since it's readable outside a Python
  environment; documented, not enforced where scikit-learn only offers `joblib`.

## Testing plan

- Unit: `TargetSpec` dispatch (label extraction, metric-function selection) for both targets;
  regression metric functions against hand-computed MAE/RMSE fixtures (same rigor as this project's
  existing hand-computed wOBA/BABIP fixture tests); the new `meta.experiment_target` FK rejects an
  unregistered target string at both the Python-config and database layers.
- Integration (against `mlb_test` only): end-to-end `run_differential` experiment through the real
  snapshot → run → compare path on a small real sample, proving idempotency (re-running produces the
  same row count, per this project's standing idempotency rule) and proving `home_win` behavior is
  byte-for-byte unchanged by the refactor (regression-proof the existing, already-verified path).
  Feature-selection stage 1/2/3 each get a fixture where the "true" informative feature and an
  injected noise column are known in advance, proving the method correctly separates them.

## Acceptance gate (extends, does not replace, Plan 04's existing gate)

- `home_win` results before this change and after are identical for the same snapshot/config
  (regression-proof, not just "still passes").
- `run_differential` baselines (zero, season-average, Pythagenpat-derived) are standing and scored
  before any ML regressor result is reported, mirroring the existing rule for `home_win`.
- Feature-selection stability reports are reproducible from snapshot ID + method configuration alone.
- No stacking, Markov-derived-feature, or neural-interaction result is reported without clearing the
  same chronological-fold, baseline-beating, out-of-fold bar already required of `home_win`'s
  existing models — an unpromoted result is recorded as a research negative, not discarded.

## Research citations (to fold into `docs/RESEARCH.md` in the implementation pass, not this spec)

- [arXiv 2511.02815 — Assessing win strength in MLB win prediction models](https://arxiv.org/abs/2511.02815)
  — already partially cited in `docs/RESEARCH.md`; this session completed the pending full read.
  Trains multiple ML models on a common dataset, relates predicted win probability to score
  differential ("win strength") — direct precedent for treating `home_win` and `run_differential` as
  related-but-distinct targets scored on the same harness.
- [MDPI/Entropy 2022 — Exploring and Selecting Features to Predict the Next Outcomes of MLB Games](https://www.mdpi.com/1099-4300/24/2/288)
  — RFE (wrapper) feature selection, honest walk-forward-style evaluation, ~65% accuracy ceiling
  reported as beating prior state of the art — supports this project's own "55-58%/70%+ is a red
  flag" calibration.
- Comparison of filter/wrapper/embedded feature selection methods (2024, *Natural Hazards* — domain
  is rockfall susceptibility, cited for the general methodology finding, not for baseball
  specifics): wrapper methods outperform filter methods but cost substantially more compute; embedded
  methods sit between both axes — directly informs section 3's three-stage design.
- Cautionary counter-example (93-94% MLB accuracy claims) traced to within-season random
  cross-validation rather than a chronological split — the leakage-class example cited in section 6.
  Source acknowledged as a secondary summary of the original study during this session; the
  implementation pass should locate and cite the primary paper directly before this claim is added to
  `docs/RESEARCH.md`, per this project's sourcing standard.
- Markov chain + neural network hybrid pattern (Markov transition features feeding an MLP; momentum-
  prediction literature) — supports section 4's "outputs as features" integration design, consistent
  with the pattern `docs/RESEARCH.md`'s stacking section already documents.
