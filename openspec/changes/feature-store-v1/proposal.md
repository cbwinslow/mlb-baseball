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
- **A machine-readable feature registry, small and separate.**
  `feature_registry.yaml` (Feast-style, ships in the package) covering **only
  the handful of published `feat.*` features**. It is deliberately *not*
  `docs/FEATURE_REGISTRY.md` — that file catalogs the ~173 internal Engine
  feature families on `gold.game_feature` and is Phase B territory. The public
  YAML is the curated toolkit surface; the two are cross-referenced, not merged.
- **A leakage-test battery that ships and runs.** `mlb_research.leakage_tests`
  — the `created_ts <= t` guarantee, the embargo check, the "shuffle the
  labels → score must worsen" test, and the "inject the outcome as a feature →
  score must collapse" test, runnable by an installing analyst against their
  own rebuild.
- **`gold.game_feature` is left alone.** It is a ~240-column internal Engine
  table wired into ~170 feature families and the paused prediction pipeline
  (`export`, `live`, `pipeline`, `audit`, …). Re-parenting it onto `feat.*` is a
  large, Phase-B-adjacent job — out of scope for this slice. `feat.*` is a
  **new standalone public layer**; it reuses the *formulas and PIT patterns*
  from the proven classical families (`team_offense_v1`'s rolling wOBA,
  `starter_prior_v1`'s pitcher form, `plate_discipline_v1`), not their tables.
  A later change may re-parent `game_feature` once `feat.*` is stable — its own
  proposal, its own owner sign-off.
- **Elo v2 + model card.** `model/elo.py` gains a probable-starter adjustment
  (starter rolling form as of first pitch, from `feat.pitcher_form` — the same
  math as the existing `starter_prior_v1` family, re-expressed at pitcher grain)
  and a preseason prior that fades; the model card (calibration, log loss,
  Brier on a strictly chronological hold-out, vs a home-field baseline and vs
  the market where available, plus stated limitations) is produced by the
  existing `model/experiment.py` harness.
- **Publication.** `mlb export` / the HF dataset gain: the `feat.player_offense`
  Parquet (the "example"), `feature_registry.yaml`, the leakage-test module, and
  the Elo v2 model card. A `notebooks/06-*.py` recipe shows `get_historical_
  features` + a walk-forward score end to end against released data only.

**Owner-confirmed 2026-09-09:** the feature table keeps raw numerators and never
edits history (D2); a minimal `feat.pitcher_form` ships now for Elo v2 (D6).

**Revised 2026-09-09 (task 1.1 audit finding):** the owner approved
"rebuild `gold.game_feature` from `feat.*`", but the audit showed
`gold.game_feature` is a ~240-column table carrying ~170 registered internal
"Engine" feature families (`docs/FEATURE_REGISTRY.md`) and feeding the paused
prediction pipeline — re-parenting it is Phase-B-adjacent and far larger than a
v1.1 slice. **`feat.*` is now a standalone public layer that reuses the proven
formulas but not the tables; `gold.game_feature` is untouched.** Re-parenting is
deferred to its own later change. Back to the owner for D5.

Out of scope (later v1.2+ changes): pitcher / team / matchup feature grains
beyond the minimum Elo v2 needs; **re-parenting `gold.game_feature` onto
`feat.*`** (its own later change); consolidating `meta.feature_snapshot` vs
`meta.experiment_snapshot` vs `gold.game_feature_snapshot` (a separate cleanup —
the prediction-ladder schema is paused); triaging the ~173 internal Engine
feature families (Phase B); any model beyond the Elo v2 reference baseline; a
hosted feature-serving API.

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

- **New:** `feat` schema + migration; `feat.player_offense` + minimal
  `feat.pitcher_form`; `mlb_baseball/sql/feat_*_build.sql`;
  `feat.asof_*` functions; `feature_registry.yaml`;
  `mlb_research.get_historical_features` + `mlb_research.leakage_tests`;
  `docs/FEATURE_STORE.md`; `notebooks/06-*.py`; Elo v2's probable-starter +
  prior code; `scripts/build_elo_v2_card.py`; `docs/models/elo-v2-card.md`;
  `tests/integration/test_feat_*.py`, `tests/unit/` for the API and leakage
  tests.
- **Changed:** `mlb_baseball/model/elo.py` (v2 — reads `feat.pitcher_form`);
  `mlb_baseball/model/experiment.py` (register Elo v2 as a baseline family);
  `mlb_baseball/export.py` + `docs/PUBLIC_API.md` (publish the feature Parquet +
  registry + card); `openspec/specs/delivery/spec.md` (via the delta);
  `openspec/project.md` (v1.1 progress); `docs/DATA_DICTIONARY.md` (the `feat`
  schema); `docs/RESEARCH.md` (the `available_ts` lag limitation);
  `docs/DECISIONS.md` (an ADR: `feat.*` is a standalone minimal public layer,
  not a re-org of `gold.game_feature` / the Engine registry).
- **NOT changed:** `gold.game_feature` and its builder; `model/features.py`; the
  ~173 internal Engine feature families; `conform.py`; ingestion; the Markov
  engine; model training. No new runtime dependency. No Phase B/C work.
- **Published dataset grows:** two new Parquet families (`feat.player_offense`,
  `feat.pitcher_form`) + three small text artifacts (registry, leakage module,
  model card).
