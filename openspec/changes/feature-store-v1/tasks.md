## 1. Audit and registry format

- [x] 1.1 Audit — done 2026-09-09. Findings: `gold.game_feature` is a
  ~240-column table carrying ~170 registered families in
  `docs/FEATURE_REGISTRY.md` (the Phase-B Engine) and is read across the paused
  prediction pipeline; `meta.feature_snapshot` fingerprints it, `meta.experiment*`
  is a working walk-forward harness with Elo already wired. **Design revised
  (see D5): `feat.*` is a standalone minimal public layer, `gold.game_feature`
  is NOT re-parented in this slice.** Still to write: `docs/FEATURE_STORE.md` —
  the public guide + a table mapping the internal snapshot/experiment tables to
  Feast vocabulary. Verify: every `meta.*` / snapshot table in `migrations/`
  appears with a one-line purpose and a keep/merge/leave note.
- [ ] 1.2 Define the `feature_registry.yaml` schema (Feast-style: per view an
  `entity`; per feature `name`, `version`, `inputs`, `availability`,
  `null_policy`) and a `mlb_research.registry` loader + validator. Verify: unit
  test — a malformed registry (missing `null_policy`) raises a clear error; a
  valid one round-trips.
- [ ] 1.3 Write the registry entries for every `feat.player_offense` and
  `feat.pitcher_form` feature this change ships. Verify: the validator passes;
  the feature count matches the built columns.

## 2. `feat` schema

- [ ] 2.1 `migrations/0104_feat_schema.sql`: `CREATE SCHEMA feat`;
  `feat.player_offense` and `feat.pitcher_form` per design D2/D6 (append-only,
  `event_ts` / `available_ts` / `created_ts` / `feature_version` / `window`,
  numerators + rates + shrunk rates, `m` + `league_prior_json`); PK
  `(entity_id, event_ts, feature_version, window)`; index on
  `(entity_id, available_ts DESC)`. Verify: `uv run mlb migrate` on a disposable
  DB succeeds and a second run is a no-op; `\d feat.player_offense` shows the PK
  and index.

## 3. `feat.player_offense` build — PostgreSQL + DuckDB parity

- [ ] 3.1 Failing integration test
  `tests/integration/test_feat_player_offense.py`: a fixture with two players
  across three games asserts one row per `(player_id, event_ts, window)`, rates
  null on a zero denominator, and a rate recomputed from summed components (not
  averaged). Verify RED without the builder, then GREEN.
- [ ] 3.2 `mlb_baseball/sql/feat_player_offense_build.sql` — rolling offensive
  counting stats and rates per window from `gold.batting_game`, empirical-Bayes
  shrunk toward the **as-of** league prior, target game excluded. Written to the
  PostgreSQL ∩ DuckDB subset (design D4): window functions / `LATERAL` / CTEs
  only, no `DISTINCT ON`, no PG procedural constructs. Verify: `sqlfluff` clean;
  the 3.1 test passes on PostgreSQL.
- [ ] 3.3 `mlb_research`-side build entry that runs the same SQL over the
  published Parquet via DuckDB (no PostgreSQL). Verify: a parity test builds the
  same fixture on both engines and asserts identical output within a documented
  float tolerance.
- [ ] 3.4 `feat.player_offense` health check in `mlb doctor` — row counts,
  null-rate bounds per feature, `available_ts >= event_ts`, no duplicate
  `(entity_id, event_ts, feature_version, window)`. Verify: the check runs in
  `test_doctor.py` against a fixture and fails on an injected duplicate.

## 4. `feat.pitcher_form` build (minimal — Elo v2's inputs only)

- [ ] 4.1 `mlb_baseball/sql/feat_pitcher_form_build.sql` — rolling batters
  faced, K−BB%, RA9 (and a FIP-like rate) per window from `gold.pitching_game`,
  same rules and engine subset as 3.2. Verify: an integration test mirrors 3.1
  for a pitcher fixture; the registry lists exactly these features and no more.

## 5. As-of retrieval

- [ ] 5.1 `feat.asof_player_offense(player_id, t)` and
  `feat.asof_pitcher_form(pitcher_id, t)` SQL functions: latest row with
  `available_ts <= t AND created_ts <= t`, else missing. Verify: an integration
  test — a request between two snapshots returns the earlier; a request before
  the first returns NULLs; a row with `created_ts > t` is not used.
- [ ] 5.2 `mlb_research.get_historical_features(entity_df, features,
  timestamp_col=...)` — Feast signature; feature refs `"<view>:<feature>"`;
  resolves against `feature_registry.yaml`; one output row per input row;
  DuckDB-over-Parquet engine. Verify: unit test — PIT-correct join on a fixture;
  an unknown feature ref raises a clear error listing valid refs; a missing
  snapshot yields a null cell, never a forward-filled value.
- [ ] 5.3 The "late data does not leak backward" scenario as an explicit test:
  ingest a pre-`t` event after `t`, assert the as-of row is unchanged, then
  rebuild and assert only rows at/after the ingest changed. Verify: red-green.

## 6. Leakage-test battery

- [ ] 6.1 `mlb_research.leakage_tests` — the four checks from design D7
  (ingest-time guarantee, embargo, label shuffle, oracle feature) as callable
  functions returning pass/fail + evidence. Verify: unit tests — each check
  fails on a deliberately leaky fixture and passes on a clean one.
- [ ] 6.2 `tests/integration/test_feat_leakage.py` runs the battery against a
  DB fixture in CI. Verify: green in CI; red when a test builder is made to peek
  one game ahead.

## 7. Reconcile with the existing feature machinery (no re-parenting)

_Re-parenting `gold.game_feature` onto `feat.*` was cut from this slice — see
D5. `gold.game_feature`, its builder, and the ~173 Engine families are untouched
here._

- [ ] 7.1 In `docs/FEATURE_STORE.md` and `feature_registry.yaml`, cross-
  reference each published `feat.*` feature to the internal family it re-uses
  the formula from (`feat.player_offense.woba_30d` ↔ `team_offense_v1`'s wOBA
  math, at player grain; `feat.pitcher_form.k_minus_bb` ↔ `starter_prior_v1`).
  Verify: every `feat.*` feature names its formula source; a reviewer can see
  the public layer duplicates no *definition*, only re-expresses proven ones at
  a new grain.
- [ ] 7.2 Note in `docs/FEATURE_STORE.md` that re-parenting `gold.game_feature`
  onto `feat.*` is a named later change (needs owner sign-off), with the reason
  (Engine / Phase B scope). Verify: the note is present and links D5.

## 8. Elo v2

- [ ] 8.1 Failing test: Elo v2's win probability for a game moves in the
  expected direction when the home probable starter's rolling K−BB% is better
  than the away starter's, all else equal. Verify RED then GREEN.
- [ ] 8.2 `model/elo.py` v2: a probable-starter adjustment reading
  `feat.asof_pitcher_form` for the probable starter available at
  `feature_cutoff_at` (not the confirmed starter), and a preseason prior that
  fades over the season's first N games. Keep v1's `expected_win_prob` /
  home-field term. Verify: `test_elo*.py` updated; `ruff` / `mypy` clean.
- [ ] 8.3 Register Elo v2 as the reference-baseline family in
  `model/experiment.py` (v1 is already wired) so the harness scores it.
  Verify: an integration test runs a 2-fold walk-forward with Elo v2 and
  produces calibration + log loss + Brier.

## 9. Model card

- [ ] 9.1 `docs/models/elo-v2-card.md` produced from a harness run: calibration
  curve/table, log loss, Brier on a strictly chronological hold-out, paired vs a
  home-field baseline and vs the market where available, plus a limitations
  section. A `scripts/build_elo_v2_card.py` regenerates it. Verify: the script
  runs against a fully-built DB and writes the card; the card names its hold-out
  and its comparison baselines.
- [ ] 9.2 A reproducibility test: running the shipped harness on the shipped
  feature store for the card's hold-out reproduces the card's numbers within the
  documented tolerance. Verify: red-green (perturb a feature, watch the number
  move outside tolerance).

## 10. Publication

- [ ] 10.1 `mlb_baseball/export.py` — allow-list `feat.player_offense` /
  `feat.pitcher_form` (`local_research`); include `feature_registry.yaml` and
  the Elo v2 card in the export manifest; ship `mlb_research.leakage_tests` in
  the wheel. Verify: `test_export*.py` pass; the manifest lists the new files.
- [ ] 10.2 `notebooks/06-feature-store-walkforward.py` — `get_historical_
  features` for a season's games at first pitch, a walk-forward Elo v2 score,
  the calibration table — **against released data only**. Verify: runs headless
  exit 0; `test_notebook_recipes.py` guard passes (no DB import).
- [ ] 10.3 Docs: `docs/DATA_DICTIONARY.md` (the `feat` schema + a snippet
  marker if the docs site should show it), `docs/FEATURE_STORE.md` (the public
  guide + Feast mapping), `docs/PUBLIC_API.md` (`get_historical_features`,
  publishing the feature Parquet), `docs/RESEARCH.md` (feature-store honest
  limitations — the `available_ts` lag assumption), `docs/DECISIONS.md` (ADR:
  `feat.*` is a standalone minimal public layer, not a re-org of
  `gold.game_feature` / the Engine registry; `feat.*` is `local_research`),
  `openspec/project.md` (v1.1 progress). Verify:
  `openspec validate --all` + `mkdocs build --strict` + `link-check` clean.

## 11. Verification

- [ ] 11.1 `openspec validate --strict feature-store-v1`; full `pre-commit`;
  `ruff` + `mypy` + `sqlfluff` on every touched file.
- [ ] 11.2 Targeted suites green: `test_feat_player_offense.py`,
  `test_feat_pitcher_form.py`, `test_feat_leakage.py`, `test_feat_asof.py`,
  the `get_historical_features` unit tests, `test_elo*.py`,
  `test_export*.py`,
  `test_notebook_recipes.py`, `test_doctor.py`.
- [ ] 11.3 Execution: `notebooks/06-*.py` runs end to end against released data;
  `scripts/build_elo_v2_card.py` writes the card; the leakage battery passes;
  the PG↔DuckDB parity test passes.
- [ ] 11.4 **Owner steps** (recorded, not CI): a full `mlb report` + feature
  build + HF publish of the v1.1 release; the Elo v2 card built against prod
  data.
