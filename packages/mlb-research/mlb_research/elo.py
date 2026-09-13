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

from dataclasses import dataclass

import numpy as np

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
