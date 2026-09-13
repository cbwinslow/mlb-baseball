"""Model-agnostic walk-forward backtest harness.

Pure numpy + pandas: no PostgreSQL, no model-training import.
`scikit-learn` appears only as this package's dev-only tie-out test
dependency (see `packages/mlb-research/tests/test_backtest.py`) and is never
imported by this module. Callers supply `fit_fn` / `predict_fn`; this module
owns fold construction, chronological train/test separation, and metrics.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from random import Random
from typing import Any, Literal

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Fold:
    name: str
    train_through: int
    test: int


@dataclass(frozen=True)
class FoldMetrics:
    fold: Fold
    metrics: dict[str, Any]
    train_rows: int
    test_rows: int
    predictions: np.ndarray


@dataclass(frozen=True)
class BacktestResult:
    folds: dict[str, FoldMetrics]
    aggregate: dict[str, Any]
    fold_plan: list[dict[str, Any]]
    coverage: dict[str, Any]
    seed: int


def time_ordered_folds(test_periods: Sequence[int], *, key: str = "season") -> tuple[Fold, ...]:
    """Build one fold per test period; train is everything strictly before it.

    `key` names the integer period column the caller filters `frame` on (e.g.
    ``season``); it does not change this function's fold math, only how the
    fold is documented/consumed downstream.
    """
    periods = tuple(test_periods)
    if not periods or tuple(sorted(set(periods))) != periods:
        raise ValueError("test periods must be unique, sorted calendar periods")
    return tuple(Fold(f"{key}-{period}", period - 1, period) for period in periods)


def drop_incomplete(frame: pd.DataFrame, required_cols: Sequence[str] = ()) -> pd.DataFrame:
    """Rows missing a value in any `required_cols` column, dropped by name
    (never positionally)."""
    complete = frame
    for column in required_cols:
        complete = complete[complete[column].notna()]
    return complete


def _split_fold(
    frame: pd.DataFrame,
    fold: Fold,
    *,
    time_col: str,
    period_col: str | None = None,
    required_cols: Sequence[str] = (),
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """Split `frame` into this fold's train/test rows.

    Rows missing a `required_cols` value are dropped (from either side) and
    counted first, by column name. Fold membership is decided by
    `period_col` (defaults to `time_col`): train is at or before the fold's
    `train_through`, test is `== fold.test`. `time_col` (the cutoff
    timestamp, which may be finer-grained than `period_col`) then gets the
    chronological-separation check lifted verbatim from `experiment.run()` --
    membership alone (e.g. matching season) does not guarantee no game in
    test actually precedes every game kept in train. Both frames are sorted
    by `time_col` (design D3): a sequential model's `predict_fn` walks test
    rows in this order, predicting from its state before folding that row's
    own outcome in -- leak-free only because the harness, not the caller,
    guarantees the order. The sort is stable, so rows sharing the same
    `time_col` value (e.g. games starting at the same instant) keep their
    relative order from `frame` rather than an arbitrary one.
    """
    period_col = period_col or time_col
    complete = drop_incomplete(frame, required_cols)
    excluded = len(frame) - len(complete)
    train = complete[complete[period_col] <= fold.train_through].sort_values(
        time_col, kind="stable"
    )
    test = complete[complete[period_col] == fold.test].sort_values(time_col, kind="stable")
    if len(train) and len(test) and train[time_col].max() >= test[time_col].min():
        raise ValueError(f"{fold.name} violates chronological cutoff separation")
    return train, test, excluded


def _logistic_irls(
    x: np.ndarray, y: np.ndarray, *, C: float = 1_000_000.0, max_iter: int = 100, tol: float = 1e-8
) -> tuple[float, float] | None:
    """1-D logistic regression (intercept + slope) fit by Newton-Raphson IRLS
    with an L2 penalty of `1/C` on the slope only (matching scikit-learn's
    `LogisticRegression(C=1e6)`, which never penalizes the intercept). The
    penalty is negligible on ordinary calibration data but keeps the fit
    finite -- and matched to sklearn's own regularized optimum -- on
    quasi-separated data, where a truly unregularized MLE has no finite
    solution. Returns `None` on a singular Hessian or non-convergence within
    `max_iter`, mirroring the existing small-sample guard's `None` fallback.
    """
    design = np.column_stack([np.ones_like(x), x])
    penalty = np.array([0.0, 1.0 / C])
    beta = np.zeros(2)
    for _ in range(max_iter):
        p = 1.0 / (1.0 + np.exp(-(design @ beta)))
        weights = np.clip(p * (1 - p), 1e-10, None)
        gradient = design.T @ (y - p) - penalty * beta
        hessian = (design * weights[:, None]).T @ design + np.diag(penalty)
        try:
            delta = np.linalg.solve(hessian, gradient)
        except np.linalg.LinAlgError:
            return None
        beta = beta + delta
        if np.max(np.abs(delta)) < tol:
            return float(beta[0]), float(beta[1])
    return None


def calibration(y: np.ndarray, probabilities: np.ndarray) -> dict[str, Any]:
    """Reliability bins plus a logistic calibration intercept/slope."""
    bins = []
    for index in range(10):
        low, high = index / 10, (index + 1) / 10
        mask = (probabilities >= low) & (
            (probabilities < high) if index < 9 else (probabilities <= high)
        )
        if mask.any():
            bins.append(
                {
                    "low": low,
                    "high": high,
                    "count": int(mask.sum()),
                    "mean_probability": float(probabilities[mask].mean()),
                    "observed_rate": float(y[mask].mean()),
                }
            )
    if len(y) < 20 or len(np.unique(y)) < 2:
        return {"bins": bins, "intercept": None, "slope": None}
    clipped = np.clip(probabilities, 1e-6, 1 - 1e-6)
    logit = np.log(clipped / (1 - clipped))
    fit = _logistic_irls(logit, y.astype(np.float64))
    if fit is None:
        return {"bins": bins, "intercept": None, "slope": None}
    intercept, slope = fit
    return {"bins": bins, "intercept": intercept, "slope": slope}


def residual_calibration(y: np.ndarray, predictions: np.ndarray) -> dict[str, Any]:
    """Regression calibration: bin games by predicted-value deciles and report
    row count, mean prediction, and mean residual (actual - predicted). A
    well-calibrated model has near-zero mean residual in every bin, not just
    a low aggregate MAE."""
    if len(y) == 0:
        return {"bins": []}
    quantiles = np.quantile(predictions, np.linspace(0.0, 1.0, 11))
    bins = []
    for index in range(10):
        low, high = float(quantiles[index]), float(quantiles[index + 1])
        mask = (predictions >= low) & ((predictions < high) if index < 9 else (predictions <= high))
        if mask.any():
            bins.append(
                {
                    "low": low,
                    "high": high,
                    "count": int(mask.sum()),
                    "mean_prediction": float(predictions[mask].mean()),
                    "mean_residual": float((y[mask] - predictions[mask]).mean()),
                }
            )
    return {"bins": bins}


def classification_metrics(y: np.ndarray, probabilities: np.ndarray, seed: int) -> dict[str, Any]:
    if (
        len(y) == 0
        or not np.isfinite(probabilities).all()
        or (probabilities < 0).any()
        or (probabilities > 1).any()
    ):
        raise ValueError("model did not produce finite probabilities in [0, 1]")
    clipped = np.clip(probabilities, 1e-15, 1 - 1e-15)
    scores: dict[str, Any] = {
        "rows": int(len(y)),
        "log_loss": float(-np.mean(y * np.log(clipped) + (1 - y) * np.log(1 - clipped))),
        "brier": float(np.mean((probabilities - y) ** 2)),
        "accuracy": float(np.mean((probabilities >= 0.5) == y)),
        "calibration": calibration(y, probabilities),
    }
    rng = Random(seed)
    samples = []
    for _ in range(200):
        indexes = [rng.randrange(len(y)) for _ in range(len(y))]
        sample_y, sample_p = y[indexes], probabilities[indexes]
        sample_clipped = np.clip(sample_p, 1e-15, 1 - 1e-15)
        samples.append(
            (
                float(
                    -np.mean(
                        sample_y * np.log(sample_clipped)
                        + (1 - sample_y) * np.log(1 - sample_clipped)
                    )
                ),
                float(np.mean((sample_p - sample_y) ** 2)),
            )
        )
    samples.sort()
    scores["log_loss_95ci"] = [samples[int(0.025 * 199)][0], samples[int(0.975 * 199)][0]]
    briers = sorted(sample[1] for sample in samples)
    scores["brier_95ci"] = [briers[int(0.025 * 199)], briers[int(0.975 * 199)]]
    return scores


def regression_metrics(y: np.ndarray, predictions: np.ndarray, seed: int) -> dict[str, Any]:
    if len(y) == 0 or not np.isfinite(predictions).all():
        raise ValueError("model did not produce finite predictions")
    scores: dict[str, Any] = {
        "rows": int(len(y)),
        "mae": float(np.mean(np.abs(y - predictions))),
        "rmse": float(np.sqrt(np.mean((y - predictions) ** 2))),
        "calibration": residual_calibration(y, predictions),
    }
    rng = Random(seed)
    samples: list[tuple[float, float]] = []
    for _ in range(200):
        indexes = [rng.randrange(len(y)) for _ in range(len(y))]
        sample_y, sample_p = y[indexes], predictions[indexes]
        samples.append(
            (
                float(np.mean(np.abs(sample_y - sample_p))),
                float(np.sqrt(np.mean((sample_y - sample_p) ** 2))),
            )
        )
    samples.sort()
    scores["mae_95ci"] = [samples[int(0.025 * 199)][0], samples[int(0.975 * 199)][0]]
    rmses = sorted(sample[1] for sample in samples)
    scores["rmse_95ci"] = [rmses[int(0.025 * 199)], rmses[int(0.975 * 199)]]
    return scores


def aggregate_metrics(fold_results: dict[str, dict[str, Any]]) -> dict[str, float | int]:
    """Row-count-weighted average of `classification_metrics` across folds."""
    rows = sum(int(metrics["rows"]) for metrics in fold_results.values())
    if rows == 0:
        raise ValueError("cannot aggregate a backtest with no scored rows")
    return {
        "rows": rows,
        "log_loss": sum(
            float(metrics["log_loss"]) * int(metrics["rows"]) for metrics in fold_results.values()
        )
        / rows,
        "brier": sum(
            float(metrics["brier"]) * int(metrics["rows"]) for metrics in fold_results.values()
        )
        / rows,
        "accuracy": sum(
            float(metrics["accuracy"]) * int(metrics["rows"]) for metrics in fold_results.values()
        )
        / rows,
    }


def aggregate_regression_metrics(fold_results: dict[str, dict[str, Any]]) -> dict[str, float | int]:
    """Row-count-weighted average of `regression_metrics` across folds."""
    rows = sum(int(metrics["rows"]) for metrics in fold_results.values())
    if rows == 0:
        raise ValueError("cannot aggregate a backtest with no scored rows")
    return {
        "rows": rows,
        "mae": sum(
            float(metrics["mae"]) * int(metrics["rows"]) for metrics in fold_results.values()
        )
        / rows,
        "rmse": sum(
            float(metrics["rmse"]) * int(metrics["rows"]) for metrics in fold_results.values()
        )
        / rows,
    }


def run_backtest(
    frame: pd.DataFrame,
    folds: Sequence[Fold],
    fit_fn: Callable[[pd.DataFrame], Any],
    predict_fn: Callable[[Any, pd.DataFrame], np.ndarray],
    *,
    task: Literal["classification", "regression"],
    time_col: str,
    label_col: str,
    feature_cols: Sequence[str],
    period_col: str | None = None,
    required_cols: Sequence[str] = (),
    seed: int = 0,
) -> BacktestResult:
    """Walk-forward evaluation: fit/predict each fold, score with the D5
    numpy metrics, and aggregate. `fit_fn`/`predict_fn` receive DataFrames
    (not matrices) so a caller keying on row identity or a sequential model
    walking `time_col` order has what it needs; a plain sklearn caller does
    `df[feature_cols].to_numpy()` in its own two-line callback -- this
    function only validates `feature_cols` are present.

    Each `FoldMetrics.predictions` is `predict_fn`'s raw output, in that
    fold's test-frame order (`_split_fold`'s, i.e. sorted by `time_col`) --
    a caller building an artifact or a `paired_comparison` needs the
    predictions themselves, not just their aggregated metrics, and can
    re-derive the matching row identities with its own `_split_fold` call
    (same fold/time_col/period_col/required_cols in, same deterministic
    row set and order out).
    """
    missing = [column for column in feature_cols if column not in frame.columns]
    if missing:
        raise ValueError(f"frame is missing feature_cols: {missing}")

    snapshot_rows = len(frame)
    common_rows = len(drop_incomplete(frame, required_cols))

    fold_plan: list[dict[str, Any]] = []
    fold_metrics: dict[str, FoldMetrics] = {}
    for fold in folds:
        fold_plan.append(
            {"name": fold.name, "train_through": fold.train_through, "test": fold.test}
        )
        train, test, _ = _split_fold(
            frame, fold, time_col=time_col, period_col=period_col, required_cols=required_cols
        )
        if train.empty or test.empty:
            raise ValueError(f"{fold.name} needs non-empty train and test rows")
        model = fit_fn(train)
        predictions = np.asarray(predict_fn(model, test))
        if predictions.shape != (len(test),):
            raise ValueError(
                f"{fold.name}: predict_fn returned shape {predictions.shape}, "
                f"expected ({len(test)},)"
            )
        labels = test[label_col].to_numpy()
        metric_seed = seed + fold.test
        metrics = (
            classification_metrics(labels, predictions, metric_seed)
            if task == "classification"
            else regression_metrics(labels, predictions, metric_seed)
        )
        fold_metrics[fold.name] = FoldMetrics(
            fold=fold,
            metrics=metrics,
            train_rows=len(train),
            test_rows=len(test),
            predictions=predictions,
        )

    aggregator = aggregate_metrics if task == "classification" else aggregate_regression_metrics
    aggregate = aggregator({name: fm.metrics for name, fm in fold_metrics.items()})

    coverage = {
        "snapshot_rows": snapshot_rows,
        "common_rows": common_rows,
        "excluded_rows": snapshot_rows - common_rows,
    }
    return BacktestResult(
        folds=fold_metrics,
        aggregate=aggregate,
        fold_plan=fold_plan,
        coverage=coverage,
        seed=seed,
    )


def paired_comparison(
    pred_a: np.ndarray,
    pred_b: np.ndarray,
    y: np.ndarray,
    keys_a: Sequence[Any],
    keys_b: Sequence[Any],
) -> dict[str, Any]:
    """The matched-sample "common games" comparison: restrict two models'
    predictions to exactly the keys both scored, so neither model is
    credited or penalized for games only it happened to cover. `y` is the
    true label aligned to `keys_a` (element i is the label for
    `keys_a[i]`); the label for a shared key is the same game regardless of
    which model produced it, so `keys_b` does not need its own labels.
    """
    labels_by_key = dict(zip(keys_a, y, strict=True))
    pred_a_by_key = dict(zip(keys_a, pred_a, strict=True))
    pred_b_by_key = dict(zip(keys_b, pred_b, strict=True))
    common_keys = sorted(set(pred_a_by_key) & set(pred_b_by_key))
    if not common_keys:
        raise ValueError("no common keys between the two models' predictions")
    return {
        "keys": common_keys,
        "count": len(common_keys),
        "y": np.array([labels_by_key[key] for key in common_keys]),
        "pred_a": np.array([pred_a_by_key[key] for key in common_keys]),
        "pred_b": np.array([pred_b_by_key[key] for key in common_keys]),
    }
