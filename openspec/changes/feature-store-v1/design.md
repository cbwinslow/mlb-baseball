## Context

See `proposal.md` — Why. Existing pieces this change builds on, not around:

- **`gold.game_feature`** — a whole-game, wide, point-in-time feature table.
  `TRUNCATE` + full rebuild; PIT safety is in the SQL (`ROWS BETWEEN UNBOUNDED
  PRECEDING AND 1 PRECEDING` — only prior completed games). Built by
  `model/features.py::build` from `mlb_baseball/sql/game_feature_rebuild.sql`.
- **`gold.game_feature_snapshot` / `meta.experiment_snapshot` /
  `meta.feature_snapshot`** — frozen training sets (feature JSON + label),
  keyed by a snapshot id, with a `data_cutoff` and an `identity_json` hash.
- **`meta.experiment` / `meta.experiment_fold` / `meta.model_run` /
  `meta.model_evaluation`** + `model/experiment.py` — a walk-forward harness:
  `folds(fold_years)` builds `train_through_season → test_season` folds;
  `_common_rows` does paired same-game comparison; `_calibration`,
  `_metrics`, `_regression_metrics` produce log loss / Brier / calibration;
  `_elo_probabilities` already runs Elo as a baseline family;
  `snapshot_integrity` is a leakage check.
- **`model/elo.py`** — team Elo + a learned home-field term. `compute_ratings`
  walks `gold.game_feature` in time order; `expected_win_prob` is the standard
  formula.
- Formulas are authored as `mlb_baseball/sql/*.sql` run by Python. SQLMesh is a
  per-table incremental re-writer adopted only after a parity tie-out, never a
  speculative parallel (ADR-266, ADR-271: "no more unpromoted SQLMesh models").
- Delivery is Parquet on Hugging Face + a `mlb-research` PyPI loader; a
  researcher has **no PostgreSQL**, only the Parquet and DuckDB.

## Goals / Non-Goals

**Goals:** an entity-grain, append-only, PIT-correct feature layer at one grain
(player offense) shaped like Feast so it is instantly familiar; a Feast-style
`get_historical_features` retrieval API; a machine-readable registry; a shipping
leakage-test battery; `gold.game_feature` re-parented to be a cache built from
the new layer; Elo v2 + a reproducible model card, built by the *existing*
harness.

**Non-Goals:** a new backtest harness (reuse `meta.experiment*`); pitcher / team
/ matchup feature grains beyond the minimum Elo v2 needs (v1.2+); consolidating
the three existing snapshot tables (separate cleanup — the prediction-ladder
schema is paused); a hosted feature-serving endpoint; any non-baseline model.

## Decisions

### D1 — reuse `meta.experiment*` as the harness; "packaging" is docs + a public entry point

The walk-forward harness exists and works. This change does **not** re-implement
it. It adds:
- a documented public entry point in `mlb_research` (a thin wrapper over the
  same fold logic) so an analyst runs the harness on the released feature store
  without cloning the repo;
- `docs/FEATURE_STORE.md` mapping the internal names to Feast vocabulary
  (`meta.experiment_snapshot` ≈ a materialized training set; `folds()` ≈
  walk-forward retrieval).
- **Alternative rejected — a fresh public harness.** Two harnesses to keep in
  sync, for no behaviour the existing one lacks.

### D2 — `feat.player_offense`: append-only, four clocks, numerators kept

```
feat.player_offense (
  player_id        bigint      NOT NULL,
  event_ts         timestamptz NOT NULL,   -- end of the last game included
  available_ts     timestamptz NOT NULL,   -- when a model may see it (event_ts + documented lag)
  created_ts       timestamptz NOT NULL,   -- when this pipeline wrote the row
  feature_version  text        NOT NULL,   -- 'v1'; a formula change is a new version, never a mutation
  window           text        NOT NULL,   -- '7d' | '14d' | '30d' | 'std'
  pa, ab, h, bb, so, hr, ...  integer,     -- summed components, always kept
  k_rate, bb_rate, woba, ...  double precision,        -- raw rates
  k_rate_shrunk, woba_shrunk  double precision,        -- empirical-Bayes toward the as-of league prior
  m, league_prior_json        ... ,        -- the shrinkage constant + priors used, for reproducibility
  PRIMARY KEY (player_id, event_ts, feature_version, window)
)
```

Rules: append-only (never `UPDATE` a historical row); a rate is null when its
denominator is zero; the league prior used for shrinkage is itself as-of (2024's
league K% cannot prime a 2023 row). Rolling windows are computed from completed
games only, excluding the target.

- **Alternative rejected — store only rates.** A rate without its exposure is
  not a feature; a 20-PA and a 600-PA `k_rate` are different objects.
- **Alternative rejected — mutate rows on a formula fix.** Breaks every
  historical training set silently. New `feature_version`, always.

### D3 — Feast-shaped retrieval

Public API mirrors Feast exactly:

```python
mlb_research.get_historical_features(
    entity_df,                       # columns: player_id (or game keys), event_timestamp
    features=["player_offense:woba_shrunk_30d", "player_offense:k_rate_shrunk_std"],
    timestamp_col="event_timestamp",
)  # -> DataFrame, one row per entity_df row, PIT-correct
```

Feature refs are `"<view>:<feature>"` strings. The **registry** is
`feature_registry.yaml` (ships in the package) — Feast-style: per view an
`entity`, and per feature `name`, `version`, `inputs`, `availability` (the
`available_ts` rule), `null_policy`. The registry is the single source of truth;
the build SQL and the API both read it.

Engine: a `feat.asof_player_offense(player_id, t)` SQL function (LATERAL "latest
row with `available_ts <= t AND created_ts <= t`") for the Postgres path; the
Python API issues the equivalent DuckDB query over Parquet for the packaged
path. Both filter on **both** `available_ts` and `created_ts`.

### D4 — one build, two engines, kept to the common SQL subset

The feature build SQL runs on **both** PostgreSQL (internal) and DuckDB (the
packaged, no-server path). It is written to the common subset: window
functions, `LATERAL`, CTEs — all supported by both. No PG-only constructs
(`DISTINCT ON` → `row_number()`, no PG procedural bits). A parity test builds
the same fixture on both and asserts identical output.

- **Alternative rejected — PG build + a separate DuckDB reimplementation.**
  Two formulas, the exact anti-pattern the project forbids.
- **Alternative rejected — ship only pre-built Parquet, no runnable build.**
  Fails the "recipe" the owner chose and the spec's "reproducible without
  PostgreSQL" requirement.

### D5 — `gold.game_feature` becomes a cache built from `feat.*`

`model/features.py::build` is re-parented: instead of its bespoke rolling-stat
SQL, it assembles the offensive feature columns via `feat.asof_player_offense`
at each game's `feature_cutoff_at`. The wide table and its snapshot flow are
unchanged downstream.

**Tie-out gate (owner-run against prod, like the Baseball-Reference tie-out):**
the re-parented `gold.game_feature` must match the current builder's output
column-by-column within a documented tolerance before the old rolling-stat SQL
is deleted. Until then both can be built and diffed.

- **Alternative rejected — leave `game_feature` on its own SQL.** Then there
  are two definitions of "player rolling wOBA before this game" — one in
  `feat.*`, one in `game_feature_rebuild.sql`.

### D6 — Elo v2 needs a *minimal* pitcher-form input

The spec's baseline is "Elo with a home-field **and probable-starter**
adjustment." The full pitcher feature grain is v1.2, so this change adds a
**minimal** `feat.pitcher_form` — only the columns Elo v2 consumes (rolling
batters-faced, K−BB%, RA9 / a FIP-like rate), same table shape and rules as
`feat.player_offense`. Elo v2 also gets a preseason prior that fades as the
season's games accumulate. The starter adjustment reads `feat.pitcher_form`
as of first pitch for each game's probable starter (probable starter is itself
a timestamped observation — use the one available at the cutoff, not the
confirmed starter).

- **Alternative rejected — Elo v2 without the starter adjustment.** Violates
  the spec's definition of the reference baseline.
- **Alternative rejected — the full pitcher grain now.** Scope blowout; the
  owner chose "one grain, done right" with pitcher/team as v1.2.

### D7 — the leakage-test battery

`mlb_research.leakage_tests` — a module an installing analyst runs against their
rebuild:
1. **Ingest-time guarantee** — for a set of `(entity, t)` requests, assert every
   contributing source row has `created_ts <= t`.
2. **Embargo** — for a feature with a W-day window, assert no training label
   within W days of a test game.
3. **Label shuffle** — shuffle only the hold-out labels; log loss must get
   materially worse (if it barely moves, the model is not using real signal).
4. **Oracle feature** — inject the actual outcome as a feature; log loss must
   collapse toward zero (proves the label truly never reaches the training
   side otherwise).
It also runs in CI against a fixture (`tests/integration/test_feat_leakage.py`).

### D8 — publication

`mlb export` / `docs/PUBLIC_API.md` gain: `feat.player_offense` +
`feat.pitcher_form` Parquet (the "example" set), `feature_registry.yaml`, the
`leakage_tests` module (shipped in the wheel), and the Elo v2 model card
(`docs/models/elo-v2-card.md`). Source-rights gate applies as for any table —
the `feat.*` builders join `core` dimensions, so they are `local_research` like
the backbone relations (a `public_safe` Retrosheet-keyed variant is future
work). `notebooks/06-feature-store-walkforward.py` demonstrates the full loop
against released data only.

## Risks / Trade-offs

- **Re-parenting `gold.game_feature` subtly shifts feature values** → the
  tie-out gate (D5); the prediction ladder that consumes it is paused, so blast
  radius is low; keep both builders until the diff is clean.
- **PostgreSQL / DuckDB SQL drift** → keep to the common subset (D4) + a parity
  test on every `feat` build SQL.
- **Elo v2's minimal `feat.pitcher_form` grows into a half-built pitcher grain**
  → the registry lists exactly the Elo-consumed features and nothing else;
  adding a feature is a v1.2 change, reviewed.
- **A fourth "snapshot/registry" artifact adds to the `meta.*` sprawl** → the
  registry is a YAML file (a different kind of thing from the snapshot tables);
  `docs/FEATURE_STORE.md` states how they relate; the consolidation is a named
  follow-up.
- **`available_ts` lag is a guess for historical rows** (Retrosheet has no
  ingest timestamp) → document the assumed lag per source; the leakage battery
  tests the mechanism, not the exact lag; a conservative default
  (`event_ts + 1 day`) is used and recorded.

## Open Questions

- Exact rolling windows (`7d / 14d / 30d / std` vs PA-based `100 / 250 / 500`) —
  tunable during implementation without changing the spec, the approach, or the
  task list.
- The empirical-Bayes shrinkage constant `m` and the league-prior grain —
  calibrated during implementation against held-out year-to-year stability.
- Hold-out season for the Elo v2 model card (2024 vs 2025) — depends on data
  completeness when the card is built; does not change the approach.
