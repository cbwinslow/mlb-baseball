## Context

See `proposal.md` — Why. `mlb_research.backtest` (feature-store-v1-harness,
done) ships `time_ordered_folds`, `run_backtest`, `paired_comparison`, and
the numpy metrics/calibration — numpy + pandas only, no database, no
model-training import, a caller-supplied `fit_fn`/`predict_fn` pair. Elo is
exactly the sequential/stateful shape that seam was built for: `run_backtest`
already guarantees a fold's test rows arrive in `time_col` order, so a
`predict_fn` can walk them predicting-before-updating without leaking a
later game into an earlier prediction (proven for the current production Elo
family in `experiment.py`'s `_elo_fit`/`_elo_step`/`_elo_predict`).

`feat.game` (feature-store-v1, done) is one row per regular-season game at
first pitch: team ids, `season`, `event_ts`, `home_win`, the home/away
starter's entering form inlined (`home_starter_fip_like_30d` etc., the
**actual** starter — `starter_is_actual = TRUE`, unconditionally, until a
probable-starter feed is wired to Retrosheet keys, which `raw.mlb_probable`'s
~5-week history cannot support today — see `proposal.md`).

## Goals / Non-Goals

**Goals:**

- One pure-numpy Elo v2 implementation in `mlb_research`, evaluated through
  the existing harness, reproducible with the public dataset alone.
- A model card comparing Elo v2 with and without its one new adjustment
  (starter quality), on identical held-out games.

**Non-Goals:**

- Probable-starter identity, a leakage-diagnostic notebook, Hugging Face
  publish wiring, or any market/production-Elo comparison — all deferred
  (`proposal.md` — What Changes).
- A general "pluggable adjustment" framework. Two knobs (fade, starter
  quality), not an extension point for a third one nobody has asked for yet.
- Tuning `FADE_GAMES` / `STARTER_WEIGHT` to a *good* value. This change picks
  defensible starting values and documents them exactly like `K_FACTOR` /
  `REVERSION_WEIGHT` already are in `mlb_baseball/model/elo.py` — "chosen,
  not sourced, revisit with backtesting evidence" — not a hyperparameter
  search.

## Decisions

### D1 — Module: `mlb_research.elo`, pure numpy, frame in

One new module, `packages/mlb-research/mlb_research/elo.py`. It takes a
`pandas.DataFrame` as input (the shape `mlb_research.backtest.run_backtest`
already consumes) rather than reading `feat.game` itself — the DuckDB read is
a separate, thin `load_game_frame(db=None) -> pd.DataFrame` function (reusing
`mlb_research.paths.resolve_db_path`, same pattern as `features.py`) so the
math is testable against a synthetic frame with no DuckDB file on disk, the
same way `mlb_research.backtest`'s own tests never touch a database.

- *Alternative — one big `build_model_card(db=None)` that reads the database
  internally.* Couples every unit test to a real DuckDB file. Rejected for
  the same reason slice 2 kept `run_backtest` frame-in: pure functions over a
  frame are trivial to test, IO is a one-line wrapper around them.

### D2 — Rating state and the fold seam

```python
@dataclass(frozen=True)
class EloV2Config:
    home_advantage: float = elo_v1.HOME_ADVANTAGE
    k_factor: float = elo_v1.K_FACTOR
    reversion_weight: float = elo_v1.REVERSION_WEIGHT
    fade_games: int = 30
    starter_weight: float = 50.0

def elo_v2_fit(train: pd.DataFrame, config: EloV2Config) -> EloV2State
def elo_v2_predict(state: EloV2State, test: pd.DataFrame, config: EloV2Config) -> np.ndarray
```

`EloV2Config` is a plain frozen dataclass so `build_model_card` can construct
two configs that differ only in `starter_weight` (D5) without duplicating any
math. `EloV2State` carries per-team `rating`, `rating_season` (last season
seen), and `games_this_season` (for the fade, D3) — the same three pieces of
state `_elo_step` already tracks, plus the counter D3 needs.
`elo_v2_fit`/`elo_v2_predict` are used directly as `run_backtest`'s
`fit_fn`/`predict_fn` (bound to a `config` via a closure or `functools.partial`
at call time); `elo_v2_predict` copies its input state before walking test
rows, exactly like `experiment.py`'s `_elo_predict`, so a second call (the
model card's second configuration) never sees state mutated by the first.

- *Alternative — a stateful `EloV2` class with `.fit()`/`.predict()`
  methods.* Closer to an sklearn shape, but the two-function form is what
  `run_backtest` already expects and what `experiment.py`'s existing Elo
  family already proved out; a class adds a constructor and an attribute
  surface for no behavioral gain here.

### D3 — Preseason fade: a continuous blend, not a bigger one-time jump

At a team's first game of a new season, `mlb_baseball/model/elo.py`'s
existing logic still runs unchanged and produces this team's **preseason
prior**: `rating * (1 - reversion_weight) + STARTING_ELO * reversion_weight`
(same formula, same constant). What changes is what happens next: instead of
using that blended value as the rating from game 1 onward, the rating fed to
`expected_win_prob` for a team's *n*-th game of the season (0-indexed) is

```
blend = min(n / fade_games, 1.0)
effective_rating = (1 - blend) * preseason_prior + blend * in_season_rating
```

where `in_season_rating` is the ordinary Elo walk (K-factor updates) starting
from `preseason_prior` at `n = 0`. At `n = 0` the two terms are identical
(`effective_rating == preseason_prior == in_season_rating`), so this is a
strict generalization of v1's jump, not a different starting point; by
`n >= fade_games` the preseason prior's direct pull is fully faded and the
model is pure within-season Elo, v1's steady state. `fade_games = 30` is a
placeholder in the same spirit as `K_FACTOR = 4`: about a fifth of a season,
chosen for a plausible "early-season evidence should matter within a few
weeks" shape, not fit to data — flagged in the module docstring exactly like
v1's unsourced constants are.

- *Alternative — an exponential fade (`blend = 1 - decay**n`).* Adds a second
  shape parameter (the decay rate) for no evidence either shape fits better;
  linear-to-a-cap is the simpler two-parameter (`fade_games`, implicit slope)
  version and is easy to reason about at the endpoints.
- *Alternative — no fade, keep v1's instant jump.* This is the literal
  request in `openspec/project.md` / the roadmap ("a preseason prior that
  fades") and the reason a real predictor's uncertainty about a new season
  should shrink game-by-game, not vanish after one blend.

### D4 — Starter-quality adjustment: an additive z-scored nudge, in points

```
quality_z(fip_like) = -(fip_like - train_mean) / train_std   # lower FIP = better = positive z
effective_home = home_rating(...) + starter_weight * quality_z(home_starter_fip_like)
effective_away = away_rating(...) + starter_weight * quality_z(away_starter_fip_like)
probability = expected_win_prob(effective_home, effective_away)   # unchanged v1 formula, home_advantage still inside it
```

`train_mean` / `train_std` of `fip_like_30d` are computed once, in
`elo_v2_fit`, from that fold's **training** rows only (both starters' values
pooled) — no test-period statistic ever enters a prediction, the same
no-leakage discipline `mlb_research.backtest`'s own required-columns
handling already enforces structurally. A missing `fip_like_30d` (a starter
with no rolling window yet, or a data gap) yields `quality_z = 0` — no
adjustment for that side, not a fabricated average — matching the project's
"missing measurement is not zero" rule literally: the team's rating is used
unadjusted, not nudged toward a guessed-neutral pitcher.

`starter_weight = 50.0` Elo points per standard deviation of `fip_like` is
the second unsourced-but-documented constant this change adds, in the same
units and spirit as `HOME_ADVANTAGE = 24`.

- *Alternative — a second small logistic/blend layer on `[elo_diff,
  starter_quality_diff]` instead of an Elo-point conversion.* Fits the two
  inputs' relative weight from data rather than hand-picking a conversion,
  but adds a second model (with its own fitting, its own leakage surface)
  on top of Elo for one feature. An additive nudge keeps Elo v2 a single
  model with two tunable constants, consistent with the K-factor/home-field
  pattern the rest of the module already uses; revisit if backtesting shows
  the fixed conversion is a poor fit.
- *Alternative — z-score against a fixed constant (e.g. `starter.py`'s
  `FIP_CONSTANT = 3.10`) instead of the fold's own train mean/std.* A fixed
  reference doesn't adapt to a fold's own run environment (FIP scale drifts
  across eras — `docs/RESEARCH.md` already documents this for the same
  constant) and, more importantly, needs an externally-sourced standard
  deviation this repo doesn't have; deriving both from train data is
  leakage-safe and self-calibrating per fold.

### D5 — The model card: two configs, one `paired_comparison`

```python
def build_model_card(
    frame: pd.DataFrame, folds: Sequence[Fold], *, config: EloV2Config = EloV2Config()
) -> dict[str, Any]

def render_model_card(result: dict[str, Any]) -> str
```

`build_model_card` runs `run_backtest` twice against the same `frame`/
`folds`: once with `config` as given (starter adjustment on), once with
`dataclasses.replace(config, starter_weight=0.0)` (the "home-field-only"
baseline — same code, one field different, no second model to maintain).
Predictions from both runs, keyed by `game_instance_key`-equivalent identity
already present in `feat.game` (`game_pk`), are passed to
`mlb_research.backtest.paired_comparison` for the matched-sample view. The
result dict carries both `BacktestResult`s' `aggregate` and `folds`, plus the
paired comparison, JSON-serializable (matches D2's existing serializability
requirement for `BacktestResult`). `render_model_card` is a pure
dict-to-markdown formatter — a calibration table per configuration, the
paired-comparison row count and metric deltas, and a fixed limitations
section (actual starter not probable; no market comparison; unsourced
constants named).

- *Alternative — compare against `mlb_baseball`'s production Elo v1
  (`gold.game_feature.home_elo`).* Requires a database connection from
  `mlb_research`, which the package's whole design (D1 here, and
  `mlb_research.backtest`'s own no-DB discipline) exists to avoid. Deferred
  per `proposal.md`; the self-comparison is a real, honest baseline (isolates
  exactly the one thing this change adds) without that dependency.

## Risks / Trade-offs

- **`fade_games` / `starter_weight` are guesses, not tuned values.** →
  Documented as such in the module docstring and the model card's
  limitations section, exactly like v1's `K_FACTOR`/`REVERSION_WEIGHT`
  already are; a follow-up backtest-driven tuning pass is expected, not
  promised here.
- **A season with very few training rows for a team makes `train_std` of
  `fip_like_30d` unstable or (degenerate case) zero.** → Guard: if
  `train_std` is zero or the pooled sample has fewer than a documented
  minimum (mirroring `mlb_research.backtest.calibration`'s own `len(y) < 20`
  guard), `quality_z` is `0` for every row in that fold rather than dividing
  by zero or amplifying noise.
- **The model card's "baseline" is Elo v2 with one field zeroed, not an
  independently-implemented baseline.** → Deliberate (D5); a real second
  implementation would risk the two diverging on something other than the
  one adjustment being measured. Revisit if a market or production-Elo
  comparison is added later (both out of scope here).

## Open Questions

- Whether `elo_v2_fit`/`elo_v2_predict`'s state (`EloV2State`) is the right
  shape for a later online/live-prediction use (not just backtesting) is
  unanswered — this change only needs the backtest path. Answerable when a
  live-prediction consumer actually exists; does not change this change's
  specs, approach, or tasks.
