"""Elo v2 -- the shipped reference baseline model (feature-store-v1-baseline).

Pure numpy: no PostgreSQL, no `sklearn`/`xgboost` import. Evaluated through
`mlb_research.backtest.run_backtest` as an ordinary `fit_fn` / `predict_fn`
pair -- Elo is exactly the sequential, predict-before-update model that seam
was built for.

Two things beyond `mlb_baseball/model/elo.py`'s already-shipped v1 math (home
field, the margin-of-victory multiplier, the K-factor update, all reused
unchanged here):

- a **preseason prior that fades**: v1's one-time reversion blend toward
  1500 at a new season's first game becomes the value a team's rating
  smoothly blends *away from* over its first `fade_games` games, rather than
  the value it jumps straight to (design D3);
- a **starter-quality adjustment**: each side's effective rating is nudged
  by its starter's entering form (`fip_like_30d`), z-scored against that
  fold's own training data so no evaluation-period statistic ever enters a
  prediction (design D4).

`FADE_GAMES` and `STARTER_WEIGHT` (in `EloV2Config`'s defaults) are, like
v1's `K_FACTOR` / `REVERSION_WEIGHT`, **chosen, not sourced** -- no
MLB-specific published value exists for either. They are real, open,
revisit-with-backtesting-evidence choices, not researched facts.

See `openspec/changes/feature-store-v1-baseline/design.md` for the full
rationale and rejected alternatives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

STARTING_ELO = 1500.0
HOME_ADVANTAGE = 24.0
K_FACTOR = 4.0
REVERSION_WEIGHT = 0.25
FADE_GAMES = 30
STARTER_WEIGHT = 50.0
MIN_FIP_SAMPLES = 20


@dataclass(frozen=True)
class EloV2Config:
    home_advantage: float = HOME_ADVANTAGE
    k_factor: float = K_FACTOR
    reversion_weight: float = REVERSION_WEIGHT
    fade_games: int = FADE_GAMES
    starter_weight: float = STARTER_WEIGHT


def _preseason_prior(prior_rating: float, reversion_weight: float) -> float:
    """v1's one-time reversion blend toward `STARTING_ELO`, unchanged --
    computed once, at a team's first game of a new season."""
    return prior_rating * (1 - reversion_weight) + STARTING_ELO * reversion_weight


def _faded_rating(
    preseason_prior: float, in_season_rating: float, games_this_season: int, fade_games: int
) -> float:
    """The rating used for prediction: a blend between the preseason prior
    and the accumulating in-season Elo walk, ramping linearly from the
    prior (at a team's first game of the season) to the plain in-season
    rating (once `fade_games` games have been played). At
    `games_this_season == 0` this equals `preseason_prior` exactly -- a
    strict generalization of v1's instant jump, not a different starting
    point (design D3)."""
    blend = min(games_this_season / fade_games, 1.0)
    return (1 - blend) * preseason_prior + blend * in_season_rating


def _quality_z(fip_like: float | None, mean: float, std: float) -> float:
    """A starter's entering-form z-score, sign-flipped so a *better*
    pitcher (lower FIP) scores positive -- design D4. `mean`/`std` come
    from that fold's own train rows only (`_fip_mean_std`), never the
    evaluation period. Missing input or a degenerate (zero/undefined)
    `std` -- guarded by the caller, `_fip_mean_std` -- yields no
    adjustment, not a fabricated average."""
    if fip_like is None or std == 0:
        return 0.0
    return -(fip_like - mean) / std


def _fip_mean_std(
    fip_values: np.ndarray, min_samples: int = MIN_FIP_SAMPLES
) -> tuple[float, float]:
    """Mean/std of a fold's pooled (home + away) train-only `fip_like_30d`
    values, for `_quality_z`. `std == 0.0` signals "no adjustment" to
    `_quality_z` -- returned here, rather than raising, whenever there are
    fewer than `min_samples` real values or they have zero variance
    (can't divide by it); same `len(y) < 20` shape as
    `mlb_research.backtest.calibration`'s own small-sample guard."""
    clean = fip_values[~np.isnan(fip_values)]
    if len(clean) < min_samples:
        return 0.0, 0.0
    std = float(clean.std())
    if std == 0.0:
        return 0.0, 0.0
    return float(clean.mean()), std


def expected_win_prob(home_rating: float, away_rating: float, home_advantage: float) -> float:
    """Standard Elo win-probability formula, home-advantage-adjusted --
    v1's math (`mlb_baseball/model/elo.py`), unchanged."""
    return 1.0 / (1.0 + 10 ** ((away_rating - (home_rating + home_advantage)) / 400.0))


def _effective_rating(team_rating: float, quality_z: float, starter_weight: float) -> float:
    """Design D4: an additive, z-scored nudge in Elo points.
    `starter_weight == 0` reproduces `team_rating` exactly regardless of
    `quality_z` -- the tie-out the model card's home-field-only baseline
    (design D5) depends on."""
    return team_rating + starter_weight * quality_z


def _mov_multiplier(score_diff: int, winner_elo: float, loser_elo: float) -> float:
    """538's general margin-of-victory multiplier -- v1's math
    (`mlb_baseball/model/elo.py`), unchanged."""
    elo_diff = max(winner_elo - loser_elo, 0.0)
    return ((abs(score_diff) + 3) ** 0.8) / (7.5 + 0.006 * elo_diff)


@dataclass
class EloV2State:
    """Mutable walk state for one fold: per-team in-season rating (the
    ordinary K-factor walk, reversion-jumped at a season boundary -- v1's
    `ratings`), the season each team was last seen in, each team's frozen
    preseason prior for this season (design D3's fade target), a
    per-season game counter, and the fold's train-only FIP mean/std
    (design D4)."""

    ratings: dict[int, float] = field(default_factory=dict)
    rating_season: dict[int, int] = field(default_factory=dict)
    preseason_prior: dict[int, float] = field(default_factory=dict)
    games_this_season: dict[int, int] = field(default_factory=dict)
    fip_mean: float = 0.0
    fip_std: float = 0.0

    def copy(self) -> EloV2State:
        return EloV2State(
            ratings=dict(self.ratings),
            rating_season=dict(self.rating_season),
            preseason_prior=dict(self.preseason_prior),
            games_this_season=dict(self.games_this_season),
            fip_mean=self.fip_mean,
            fip_std=self.fip_std,
        )


def _elo_v2_step(state: EloV2State, row: Any, config: EloV2Config) -> float:
    """One Elo v2 prediction-then-update step, shared by `elo_v2_fit`
    (replaying history to build state) and `elo_v2_predict` (walking test
    rows). Mutates `state` in place; returns the predicted home-win
    probability for `row`, computed before `row`'s own outcome is folded
    in."""
    home, away = row.home_team_id, row.away_team_id
    for team in (home, away):
        if team not in state.ratings:
            state.ratings[team] = STARTING_ELO
            state.preseason_prior[team] = STARTING_ELO
            state.games_this_season[team] = 0
        elif state.rating_season[team] != row.season:
            state.ratings[team] = _preseason_prior(state.ratings[team], config.reversion_weight)
            state.preseason_prior[team] = state.ratings[team]
            state.games_this_season[team] = 0
        state.rating_season[team] = row.season

    home_faded = _faded_rating(
        state.preseason_prior[home],
        state.ratings[home],
        state.games_this_season[home],
        config.fade_games,
    )
    away_faded = _faded_rating(
        state.preseason_prior[away],
        state.ratings[away],
        state.games_this_season[away],
        config.fade_games,
    )
    home_z = _quality_z(row.home_starter_fip_like_30d, state.fip_mean, state.fip_std)
    away_z = _quality_z(row.away_starter_fip_like_30d, state.fip_mean, state.fip_std)
    home_effective = _effective_rating(home_faded, home_z, config.starter_weight)
    away_effective = _effective_rating(away_faded, away_z, config.starter_weight)

    probability = expected_win_prob(home_effective, away_effective, config.home_advantage)

    if row.home_win:
        score_diff = max(1, row.home_score - row.away_score)
        mult = _mov_multiplier(score_diff, home_effective + config.home_advantage, away_effective)
        state.ratings[home] += config.k_factor * mult * (1 - probability)
        state.ratings[away] += config.k_factor * mult * (probability - 1)
    else:
        score_diff = max(1, row.away_score - row.home_score)
        mult = _mov_multiplier(score_diff, away_effective, home_effective + config.home_advantage)
        state.ratings[home] += config.k_factor * mult * (0 - probability)
        state.ratings[away] += config.k_factor * mult * (probability - 0)
    state.games_this_season[home] += 1
    state.games_this_season[away] += 1
    return probability


def _pooled_fip(frame: pd.DataFrame) -> np.ndarray:
    return np.concatenate(
        [
            frame["home_starter_fip_like_30d"].to_numpy(dtype=np.float64),
            frame["away_starter_fip_like_30d"].to_numpy(dtype=np.float64),
        ]
    )


def elo_v2_fit(train: pd.DataFrame, config: EloV2Config | None = None) -> EloV2State:
    """`fit_fn` for `mlb_research.backtest.run_backtest`: replay every train
    row (already time-ordered by `run_backtest`) to build the rating state
    as of the fold boundary, plus this fold's train-only FIP mean/std."""
    config = config or EloV2Config()
    fip_mean, fip_std = _fip_mean_std(_pooled_fip(train))
    state = EloV2State(fip_mean=fip_mean, fip_std=fip_std)
    for row in train.itertuples():
        _elo_v2_step(state, row, config)
    return state


def elo_v2_predict(
    state: EloV2State, test: pd.DataFrame, config: EloV2Config | None = None
) -> np.ndarray:
    """`predict_fn` for `run_backtest`: continue the walk over test rows
    (also time-ordered by `run_backtest`), copying the fitted state so
    repeated calls never mutate it -- the model card (design D5) calls this
    twice from the same fitted state with two different configs' starter
    weight. Leak-free because `run_backtest` guarantees `time_col` order
    and this predicts before each row's own update."""
    config = config or EloV2Config()
    walked = state.copy()
    return np.array(
        [_elo_v2_step(walked, row, config) for row in test.itertuples()], dtype=np.float64
    )
