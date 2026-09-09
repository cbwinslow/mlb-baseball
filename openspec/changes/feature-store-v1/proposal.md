## Why

`openspec/project.md` defines v1.1 as the release that turns the research
database into a *platform*: a point-in-time feature store, a walk-forward
backtest harness, and one reference baseline model (Elo v2) + its model card.
The `delivery` capability already specifies what the public feature store must
be — "append-only feature snapshot tables keyed by entity and an availability
timestamp, an as-of retrieval contract …, a machine-readable feature registry
…, and a leakage-test battery." None of it ships yet.

Much of the machinery already exists internally, for the paused prediction
ladder: `gold.game_feature` is a working point-in-time (whole-game) feature
table, and `meta.experiment` / `meta.experiment_fold` / `meta.model_run` /
`meta.model_evaluation` plus `model/experiment.py` are a working walk-forward
harness with calibration/log-loss/Brier scoring and Elo already wired in as a
baseline family. The gap is not "build a harness" — it is: (1) there is no
entity-grain, append-only feature layer the spec calls for; (2) none of it is
packaged or documented for an outside researcher; (3) there is no Elo v2 or
model card.

This change delivers the **first coherent slice**: the feature store at one
grain (player rolling offensive rates), Feast-shaped so it is familiar to
anyone who has used a feature store, with Elo v2 as the worked example that
consumes it and proves it works end to end.

## What Changes

- **New `feat` schema, one grain to start.** `feat.player_offense` —
  append-only, one row per `(player_id, event_ts, feature_version)`, carrying
  `available_ts` and `created_ts` (see design D2), rolling offensive counting
  stats and shrunk rates at several windows (7 / 14 / 30 days and
  season-to-date), numerators and denominators kept alongside every rate. Built
  by `mlb_baseball/sql/*.sql`, run by Python — **no SQLMesh model** (ADR-266 /
  ADR-271). The build SQL is DuckDB-compatible so it also runs over the
  published Parquet with no Postgres (see design D4).
- **A Feast-shaped retrieval contract.**
  `mlb_research.get_historical_features(entity_df, features, timestamp_col=...)`
  — hand it `(entity, decision-time)` rows, get back a point-in-time-correct
  frame, one row per input, each feature the latest snapshot with
  `available_ts <= t` **and** `created_ts <= t`; a missing snapshot returns
  missing, never filled forward. A `feat.asof_player_offense(player_id, t)` SQL
  function is the Postgres-side engine; the Python API works on DuckDB-over-
  Parquet for the packaged case.
- **A machine-readable feature registry.** `feature_registry.yaml` (Feast-style,
  ships in the package): every feature's name, entity, version, inputs,
  availability rule, and null policy. It is the single source of truth for
  feature definitions.
- **A leakage-test battery that ships and runs.** `mlb_research.leakage_tests`
  — the `created_ts <= t` guarantee, the embargo check, the "shuffle the
  labels → score must worsen" test, and the "inject the outcome as a feature →
  score must collapse" test, runnable by an installing analyst against their
  own rebuild.
- **`gold.game_feature` re-parented, not replaced.** Its builder assembles from
  `feat.*` as-of joins instead of its current bespoke SQL (Option 3 — the
  entity layer is the source of truth, the wide game row is a materialized
  cache). Behaviour-preserving: the rebuilt `gold.game_feature` ties out to the
  current one within a documented tolerance before the switch.
- **Elo v2 + model card.** `model/elo.py` gains a probable-starter adjustment
  (starter rolling form as of first pitch, from `feat.*`) and a preseason prior
  that fades; the model card (calibration, log loss, Brier on a strictly
  chronological hold-out, vs a home-field baseline and vs the market where
  available, plus stated limitations) is produced by the existing
  `model/experiment.py` harness.
- **Publication.** `mlb export` / the HF dataset gain: the `feat.player_offense`
  Parquet (the "example"), `feature_registry.yaml`, the leakage-test module, and
  the Elo v2 model card. A `notebooks/06-*.py` recipe shows `get_historical_
  features` + a walk-forward score end to end against released data only.

Out of scope (later v1.2+ changes): pitcher / team / matchup feature grains;
consolidating `meta.feature_snapshot` vs `meta.experiment_snapshot` vs
`gold.game_feature_snapshot` (a separate cleanup — the prediction-ladder schema
is paused, this change only documents it and adds the new registry alongside);
any model beyond the Elo v2 reference baseline; a hosted feature-serving API.

## Capabilities

### New Capabilities

_None — the `delivery` capability already specifies the feature store and the
reference baseline._

### Modified Capabilities

- `delivery`: tighten two requirements. The feature-store requirement gains the
  **ingest-time (`created_ts`) guarantee** (a feature for decision time `t` uses
  only records the warehouse had *ingested* by `t`, not merely records whose
  event time is `<= t`) and the **rebuildable-without-Postgres** guarantee (the
  packaged build runs on DuckDB over the published Parquet). The reference-
  baseline requirement gains that the baseline's model card is produced by the
  same harness the distribution ships, so an analyst can reproduce its numbers.

## Impact

- **New:** `feat` schema + migration; `mlb_baseball/sql/feat_player_offense_*.sql`;
  `feat.asof_player_offense` function; `feature_registry.yaml`;
  `mlb_research.get_historical_features` + `mlb_research.leakage_tests`;
  `notebooks/06-*.py`; Elo v2's probable-starter + prior code;
  `tests/integration/test_feat_player_offense.py`, `tests/unit/` for the API and
  leakage tests.
- **Changed:** `mlb_baseball/model/features.py` (re-parented to assemble from
  `feat.*`); `mlb_baseball/model/elo.py` (v2); `mlb_baseball/export.py` +
  `docs/PUBLIC_API.md` (publish the feature Parquet + registry + card);
  `openspec/specs/delivery/spec.md` (via the delta); `openspec/project.md`
  (v1.1 progress); `docs/DATA_DICTIONARY.md` (the `feat` schema);
  `docs/RESEARCH.md` / a new `docs/FEATURE_STORE.md`; `docs/DECISIONS.md` (an
  ADR for the entity-layer + `game_feature`-as-cache decision).
- **Tie-out gate:** the re-parented `gold.game_feature` must match the current
  builder's output within a documented tolerance (owner-run against prod, like
  the Baseball-Reference tie-out) before the old builder is removed.
- **No** change to `conform.py` identity, ingestion, the Markov engine, or model
  training. **No** new runtime dependency. **No** Phase B/C work — the reference
  baseline and the public harness are explicitly Phase A / v1.1.
- **Published dataset grows:** one new Parquet family (`feat.player_offense`) +
  three small text artifacts (registry, leakage module, model card).
