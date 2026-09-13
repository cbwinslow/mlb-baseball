Scope: ship `mlb_research.elo` (Elo v2: v1's math + a fading preseason prior +
a starter-quality adjustment) and its model card, both pure numpy, evaluated
through the existing `mlb_research.backtest` harness. Probable-starter data,
the leakage-diagnostic notebook, HF publish wiring, and any market/production-
Elo comparison are explicitly out of scope (`proposal.md`).

TDD applies to every task that adds behaviour: write the failing test, watch
it fail for the right reason, then make it pass.

## 1. Module setup

- [x] 1.1 Create `packages/mlb-research/mlb_research/elo.py` with the module
  docstring (pure numpy, no database, no `sklearn`/`xgboost`; states
  `FADE_GAMES`/`STARTER_WEIGHT` are chosen, not sourced, same as
  `mlb_baseball/model/elo.py`'s `K_FACTOR`/`REVERSION_WEIGHT`) and the
  `EloV2Config` frozen dataclass (design D2: `home_advantage`, `k_factor`,
  `reversion_weight`, `fade_games=30`, `starter_weight=50.0`). Verify:
  `import mlb_research.elo` succeeds; `ruff` + `mypy` clean.
- [x] 1.2 Add `packages/mlb-research/tests/test_elo.py`. Verify: `pytest
  packages/mlb-research/tests/test_elo.py` collects (even with zero tests
  yet).

## 2. Preseason fade

- [x] 2.1 Failing test: a team with a known prior-season ending rating,
  walking into a new season, produces `effective_rating == preseason_prior`
  exactly at the season's first game (`n=0`) and converges to the plain
  in-season Elo walk once `n >= fade_games`, with a value strictly between
  the two at a mid-fade game — hand-computed expected values for all three
  points. Verify: RED then GREEN.
- [x] 2.2 Implement the fade (design D3): the blend
  `effective_rating = (1-blend)*preseason_prior + blend*in_season_rating`,
  `blend = min(n/fade_games, 1.0)`, `preseason_prior` computed with v1's
  existing one-time reversion formula at a team's first game of a season.
  Verify: 2.1 passes.
- [x] 2.3 Failing test: two teams that have never appeared before (first
  game of the dataset for both) start at `STARTING_ELO` with `blend=0`
  (i.e. `n=0` for a team's literal first game behaves the same whether or
  not a "prior season" exists). Verify: RED then GREEN; implement any gap 2.2
  left uncovered.

## 3. Starter-quality adjustment

- [x] 3.1 Failing test: given a small train frame with known
  `home_starter_fip_like_30d`/`away_starter_fip_like_30d` values,
  `quality_z` of a known FIP value matches a hand-computed z-score
  (mean/std over the pooled home+away train values), sign such that a lower
  FIP (better pitcher) gives a positive z. Verify: RED then GREEN.
- [x] 3.2 Implement train-only mean/std computation and `quality_z` (design
  D4), computed once per fold inside `elo_v2_fit` and closed over by the
  returned state/callable for use in `elo_v2_predict`. Verify: 3.1 passes.
- [x] 3.3 Failing test: a test row with a null `fip_like_30d` for one side
  gets `quality_z = 0` for that side (unadjusted rating), while the other
  side's real value still applies normally. Verify: RED then GREEN.
- [x] 3.4 Failing test: a train fold where pooled `fip_like_30d` values have
  zero variance (or fewer than a documented minimum count) does not raise
  or divide by zero — every `quality_z` in that fold is `0`. Verify: RED
  then GREEN; implement the guard (design Risks).
- [x] 3.5 Implement `effective_rating = team_rating + starter_weight *
  quality_z(...)` feeding into the existing `expected_win_prob` (home
  advantage unchanged, inside that call). Verify: a unit test with
  `starter_weight=0` reproduces the fade-only rating from section 2 exactly
  (no adjustment when the weight is zero, independent of `quality_z`'s
  value) — this is the tie-out design D5's model-card baseline depends on.

## 4. `fit_fn` / `predict_fn` for `run_backtest`

- [ ] 4.1 Failing test: `elo_v2_fit(train, config)` replays a small
  chronologically-ordered train frame (reusing the sequential-walk pattern
  from `mlb_research.backtest`'s own Elo test, `test_run_backtest_delivers_
  test_rows_in_time_col_order_for_sequential_models`) and returns a state
  whose ratings match a hand roll incorporating both the fade (section 2)
  and the starter adjustment (section 3). Verify: RED then GREEN.
- [ ] 4.2 Failing test: `elo_v2_predict(state, test, config)` walks test rows
  in the order given (relying on `run_backtest` to have sorted them),
  predicts before updating with each row's own outcome, and calling it twice
  from the same fitted state (as the model card's two configurations will,
  design D5) produces identical results both times — the state is not
  mutated by a call. Verify: RED then GREEN.
- [ ] 4.3 Implement `elo_v2_fit` / `elo_v2_predict` (design D2), reusing
  `mlb_baseball/model/elo.py`'s `_mov_multiplier` shape and constants
  (`HOME_ADVANTAGE`, default `K_FACTOR`, `REVERSION_WEIGHT`) translated into
  this module — pure numpy, no import from `mlb_baseball`. Verify: 4.1 and
  4.2 pass.
- [ ] 4.4 Integration test: `run_backtest(frame, folds, elo_v2_fit_fn,
  elo_v2_predict_fn, task="classification", ...)` over a synthetic
  multi-season frame with team ids, `event_ts`, `season`, `home_win`, and
  starter FIP columns completes and returns per-fold and aggregate
  probability-quality metrics, matching a hand roll of the same fold on the
  same fixture. Verify: RED then GREEN.
- [ ] 4.5 Dependency-direction check: subprocess `sys.modules` assertion that
  importing `mlb_research.elo` pulls in neither `sklearn` nor `xgboost`
  (same pattern as `mlb_research.backtest`'s own
  `test_module_imports_without_sklearn_or_xgboost`). Verify: passes.

## 5. Data loading

- [ ] 5.1 Failing test: `load_game_frame(db=<a small fixture DuckDB file with
  a feat.game table>)` returns a `DataFrame` with the columns `elo_v2_fit`/
  `elo_v2_predict` need (team ids, `event_ts`, `season`, `home_win`, starter
  FIP columns, `game_pk`), one row per `feat.game` row. Verify: RED then
  GREEN.
- [ ] 5.2 Implement `load_game_frame(db=None) -> pd.DataFrame` using
  `mlb_research.paths.resolve_db_path` and a direct `duckdb.connect(...)
  .sql("SELECT * FROM feat.game")` (no ASOF join needed — this reads the
  whole table, not a point-in-time entity join). Verify: 5.1 passes; `ruff`
  + `mypy` clean.

## 6. The model card

- [ ] 6.1 Failing test: `build_model_card(frame, folds)` on a synthetic
  multi-season frame returns a result whose two configurations'
  (`starter_weight` as given vs. `0.0`) `BacktestResult`s are present, and
  whose `starter_weight=0.0` run's per-fold metrics exactly match a direct
  `run_backtest` call using `elo_v2_fit`/`elo_v2_predict` bound to a
  `dataclasses.replace(config, starter_weight=0.0)` config on the same
  fixture — proves the model card's "baseline" call is not silently
  different from calling the harness directly. Verify: RED then GREEN.
- [ ] 6.2 Implement `build_model_card` (design D5): two `run_backtest` calls
  sharing `frame`/`folds`, `paired_comparison` between their predictions
  keyed by `game_pk`, assembled into one JSON-serializable result dict.
  Verify: 6.1 passes; `json.dumps(result)` round-trips without error on a
  real (non-mocked) result.
- [ ] 6.3 Failing test: `render_model_card(result)` produces a markdown
  string containing both configurations' log loss/Brier/calibration, the
  paired-comparison row count, and a limitations section (actual starter
  not probable; no market comparison; `FADE_GAMES`/`STARTER_WEIGHT`
  unsourced). Verify: RED then GREEN.
- [ ] 6.4 Implement `render_model_card`. Verify: 6.3 passes.

## 7. Documentation

- [ ] 7.1 `packages/mlb-research/README.md`: a "Reference baseline: Elo v2"
  section under or near "Backtesting" — `EloV2Config`, `elo_v2_fit`/
  `elo_v2_predict` as a `fit_fn`/`predict_fn` pair, `build_model_card`/
  `render_model_card`, a copy-pasteable example running the card against a
  local `mlb build` output. Verify: the example runs in a clean env with
  `mlb-research` only (no `sklearn`/`xgboost`/database).
- [ ] 7.2 `docs/PUBLIC_API.md` / `docs/RESEARCH.md` / `mlb_baseball/model/
  AGENTS.md`: note the reference baseline now ships in `mlb_research.elo`,
  point to it; `mlb_baseball/model/elo.py` (v1) is unchanged and separate.
  Verify: `mkdocs build --strict` clean.
- [ ] 7.3 Update `openspec/project.md`'s `NOW/NEXT/LATER` (slice 3 done, this
  narrowed scope) and `openspec/changes/feature-store-v1/proposal.md`'s
  Roadmap section (slice 3 entry). Verify: `openspec validate --all` passes.

## 8. Verification

- [ ] 8.1 `openspec validate --strict feature-store-v1-baseline`; full
  `pre-commit`; `ruff check` + `ruff format --check` + `mypy` on every
  touched file. Verify: each command's exit code recorded.
- [ ] 8.2 Targeted suites green:
  `packages/mlb-research/tests/test_elo.py` (new), plus
  `packages/mlb-research/tests/` as a whole (no regression in the harness
  or feature-store tests already there). Verify: run and record counts.
- [ ] 8.3 **[OWNER]** Run the model card against a real local `mlb build`
  output (or the production DuckDB build, read-only) and read the rendered
  markdown for plausibility (log loss/Brier in a sane range, calibration
  bins populated, no NaNs) — a human sanity check the automated tests can't
  substitute for. Not CI-gated.
