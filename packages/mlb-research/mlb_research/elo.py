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

import os
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from functools import partial
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from mlb_research import backtest
from mlb_research.paths import resolve_db_path

_TIME_COL = "event_ts"
_PERIOD_COL = "season"
_LABEL_COL = "home_win"
_FEATURE_COLS = ("home_starter_fip_like_30d", "away_starter_fip_like_30d")
_KEY_COL = "game_pk"

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

    def __post_init__(self) -> None:
        if self.fade_games <= 0:
            raise ValueError(f"fade_games must be positive, got {self.fade_games}")


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
    adjustment, not a fabricated average. `pd.isna` (not `fip_like is
    None`) catches both a literal `None` and a pandas `NaN` -- a
    DataFrame column's missing float value from `.itertuples()` is
    `float('nan')`, and `nan is None` is `False`, so a `None`-only check
    would silently let `NaN` propagate into the rating instead."""
    if fip_like is None or pd.isna(fip_like) or std == 0:
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


def _serialize_backtest_result(result: backtest.BacktestResult) -> dict[str, Any]:
    return {
        "aggregate": result.aggregate,
        "coverage": result.coverage,
        "seed": result.seed,
        "fold_plan": result.fold_plan,
        "folds": {
            name: {
                "metrics": fm.metrics,
                "train_rows": fm.train_rows,
                "test_rows": fm.test_rows,
                "predictions": fm.predictions.tolist(),
            }
            for name, fm in result.folds.items()
        },
    }


def _fold_test_keys(frame: pd.DataFrame, folds: Sequence[backtest.Fold]) -> dict[str, list[Any]]:
    """Each fold's test-row `game_pk`s, in the same deterministic order
    `run_backtest`'s internal split produces (`period_col` membership, then
    a stable sort by `time_col`) -- so `FoldMetrics.predictions` (returned
    in that same order) can be matched back to a game identity."""
    keys: dict[str, list[Any]] = {}
    for fold in folds:
        test = frame[frame[_PERIOD_COL] == fold.test].sort_values(_TIME_COL, kind="stable")
        keys[fold.name] = list(test[_KEY_COL])
    return keys


def _flatten_predictions(
    result: backtest.BacktestResult, fold_keys: dict[str, list[Any]]
) -> tuple[list[Any], np.ndarray]:
    all_keys: list[Any] = []
    all_predictions: list[float] = []
    for name, fold_metrics in result.folds.items():
        all_keys.extend(fold_keys[name])
        all_predictions.extend(fold_metrics.predictions.tolist())
    return all_keys, np.array(all_predictions, dtype=np.float64)


def build_model_card(
    frame: pd.DataFrame,
    folds: Sequence[backtest.Fold],
    config: EloV2Config | None = None,
) -> dict[str, Any]:
    """Design D5: backtest Elo v2 twice -- `config` as given, and again
    with `starter_weight=0.0` (a home-field-only baseline, same model, one
    field different) -- then `paired_comparison` the two over identical
    evaluation games. No database, no market data: `frame` is the caller's
    own `load_game_frame()` output (or an equivalent `feat.game`-shaped
    frame)."""
    config = config or EloV2Config()
    baseline_config = replace(config, starter_weight=0.0)

    def run(cfg: EloV2Config) -> backtest.BacktestResult:
        return backtest.run_backtest(
            frame,
            folds,
            partial(elo_v2_fit, config=cfg),
            partial(elo_v2_predict, config=cfg),
            task="classification",
            time_col=_TIME_COL,
            period_col=_PERIOD_COL,
            label_col=_LABEL_COL,
            feature_cols=_FEATURE_COLS,
        )

    adjusted_result = run(config)
    baseline_result = run(baseline_config)

    fold_keys = _fold_test_keys(frame, folds)
    adjusted_keys, adjusted_predictions = _flatten_predictions(adjusted_result, fold_keys)
    baseline_keys, baseline_predictions = _flatten_predictions(baseline_result, fold_keys)
    labels_by_key = dict(zip(frame[_KEY_COL], frame[_LABEL_COL].astype(float), strict=True))
    labels = np.array([labels_by_key[key] for key in adjusted_keys], dtype=np.float64)

    matched = backtest.paired_comparison(
        adjusted_predictions, baseline_predictions, labels, adjusted_keys, baseline_keys
    )
    adjusted_matched_metrics = backtest.classification_metrics(matched["y"], matched["pred_a"], 0)
    baseline_matched_metrics = backtest.classification_metrics(matched["y"], matched["pred_b"], 0)

    return {
        "config": {
            "home_advantage": config.home_advantage,
            "k_factor": config.k_factor,
            "reversion_weight": config.reversion_weight,
            "fade_games": config.fade_games,
            "starter_weight": config.starter_weight,
        },
        "adjusted": _serialize_backtest_result(adjusted_result),
        "baseline": _serialize_backtest_result(baseline_result),
        "comparison": {
            "count": matched["count"],
            "adjusted_metrics": adjusted_matched_metrics,
            "baseline_metrics": baseline_matched_metrics,
            "log_loss_delta": (
                baseline_matched_metrics["log_loss"] - adjusted_matched_metrics["log_loss"]
            ),
        },
    }


def render_model_card(result: dict[str, Any]) -> str:
    """A plain markdown rendering of `build_model_card`'s result: both
    configurations' probability-quality metrics, the matched-sample
    comparison, and a fixed limitations section."""
    lines = ["# Elo v2 model card", "", "## Configuration"]
    for key, value in result["config"].items():
        lines.append(f"- `{key}`: {value}")

    for label, section in (
        ("Starter adjustment ON", "adjusted"),
        ("Starter adjustment OFF (home-field baseline)", "baseline"),
    ):
        aggregate = result[section]["aggregate"]
        lines += [
            "",
            f"## {label}",
            f"- rows: {aggregate['rows']}",
            f"- log loss: {aggregate['log_loss']:.4f}",
            f"- brier: {aggregate['brier']:.4f}",
            f"- accuracy: {aggregate['accuracy']:.4f}",
            "",
            "### Calibration by fold",
        ]
        for fold_name, fold in result[section]["folds"].items():
            calibration = fold["metrics"]["calibration"]
            lines.append(
                f"- {fold_name}: intercept={calibration['intercept']}, slope={calibration['slope']}"
            )

    comparison = result["comparison"]
    lines += [
        "",
        "## Matched-sample comparison",
        f"- games compared: {comparison['count']}",
        f"- adjusted log loss: {comparison['adjusted_metrics']['log_loss']:.4f}",
        f"- baseline log loss: {comparison['baseline_metrics']['log_loss']:.4f}",
        f"- log loss delta (baseline - adjusted): {comparison['log_loss_delta']:.4f}",
        "",
        "## Limitations",
        "- Uses the **actual** starting pitcher, not the probable one "
        "(`feat.game`'s `starter_is_actual = TRUE`) -- a probable-starter "
        "feed does not yet have enough history to backtest against.",
        "- No betting-market comparison. The baseline above is Elo v2 with "
        "the starter adjustment disabled, not an independent model or the "
        "market.",
        f"- `FADE_GAMES`={result['config']['fade_games']} and "
        f"`STARTER_WEIGHT`={result['config']['starter_weight']} are chosen, "
        "not sourced from published research; revisit with backtesting "
        "evidence.",
    ]
    return "\n".join(lines)


def load_game_frame(db: str | os.PathLike[str] | None = None) -> pd.DataFrame:
    """The whole `feat.game` table (feature-store-v1), one row per
    regular-season game, as a plain `DataFrame` -- no point-in-time entity
    join needed here (unlike `get_historical_features`): a backtest wants
    every row, not an as-of lookup against an entity frame."""
    path = resolve_db_path(db)
    con = duckdb.connect(str(path), read_only=True)
    try:
        return con.sql("SELECT * FROM feat.game").df()
    finally:
        con.close()
