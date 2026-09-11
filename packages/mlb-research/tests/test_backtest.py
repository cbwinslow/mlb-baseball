import math
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest
from mlb_research import backtest


def test_calendar_folds_are_strictly_ordered():
    assert backtest.time_ordered_folds((2016, 2017)) == (
        backtest.Fold("season-2016", 2015, 2016),
        backtest.Fold("season-2017", 2016, 2017),
    )
    with pytest.raises(ValueError, match="unique, sorted"):
        backtest.time_ordered_folds((2017, 2016))


def test_split_fold_excludes_null_required_rows_selected_by_name():
    # "other" sorts before "rate" so a positional (not name-based) null check
    # would look at the wrong column and miss the nulls in "rate".
    frame = pd.DataFrame(
        {
            "other": [1.0, 2.0, 3.0, 4.0],
            "season": [2015, 2015, 2016, 2016],
            "rate": [0.1, None, 0.3, None],
        }
    )
    fold = backtest.Fold("season-2016", 2015, 2016)

    train, test, excluded = backtest._split_fold(
        frame, fold, time_col="season", required_cols=("rate",)
    )

    assert list(train["other"]) == [1.0]
    assert list(test["other"]) == [3.0]
    assert excluded == 2


def test_split_fold_rejects_overlapping_time_col_values():
    # season boundaries look fine, but the same time_col value straddles both
    # sides -- this is exactly the leak the assert exists to catch.
    frame = pd.DataFrame({"season": [2015, 2016, 2016], "cutoff": [2016, 2016, 2017]})
    fold = backtest.Fold("season-2016", 2015, 2016)

    with pytest.raises(ValueError, match="chronological cutoff separation"):
        backtest._split_fold(frame, fold, time_col="cutoff", period_col="season")


def test_split_fold_sort_is_stable_for_tied_time_col_values():
    # Games can share an exact start time; a sequential model (Elo) walking
    # test rows needs a deterministic tie-break, not whatever an unstable
    # sort happens to produce -- so ties keep their relative order from the
    # input frame.
    frame = pd.DataFrame(
        {
            "season": [2016] * 6,
            "cutoff": [1, 1, 1, 1, 1, 1],
            "row_id": ["f", "e", "d", "c", "b", "a"],
        }
    )
    fold = backtest.Fold("season-2016", 2015, 2016)

    _, test, _ = backtest._split_fold(frame, fold, time_col="cutoff", period_col="season")

    assert list(test["row_id"]) == ["f", "e", "d", "c", "b", "a"]


def test_probability_metrics_match_hand_calculation_and_are_deterministic():
    actual = np.array([1, 0])
    probabilities = np.array([0.75, 0.25])

    first = backtest.classification_metrics(actual, probabilities, seed=7)
    second = backtest.classification_metrics(actual, probabilities, seed=7)

    # Brier = ((.75 - 1)^2 + (.25 - 0)^2) / 2 = .0625.
    assert first["brier"] == pytest.approx(0.0625)
    # Log loss = -log(.75) when both samples receive the same probability
    # assigned to the observed class.
    assert first["log_loss"] == pytest.approx(-math.log(0.75))
    assert first["accuracy"] == 1.0
    assert first["log_loss_95ci"] == second["log_loss_95ci"]
    assert first["calibration"]["intercept"] is None
    assert first["calibration"]["bins"] == [
        {
            "low": 0.2,
            "high": 0.3,
            "count": 1,
            "mean_probability": 0.25,
            "observed_rate": 0.0,
        },
        {
            "low": 0.7,
            "high": 0.8,
            "count": 1,
            "mean_probability": 0.75,
            "observed_rate": 1.0,
        },
    ]


def test_regression_metrics_match_hand_calculation_and_are_deterministic():
    # Hand-computed test vectors:
    # actual:      [3.0, -1.0, 4.0,  0.0]
    # predictions: [2.0,  1.0, 4.0, -2.0]
    # errors (act - pred): [1.0, -2.0, 0.0, 2.0]
    # abs errors: [1.0, 2.0, 0.0, 2.0] -> MAE = (1 + 2 + 0 + 2) / 4 = 1.25
    # sq errors:  [1.0, 4.0, 0.0, 4.0] -> MSE = (1 + 4 + 0 + 4) / 4 = 2.25 -> RMSE = 1.5
    actual = np.array([3.0, -1.0, 4.0, 0.0])
    predictions = np.array([2.0, 1.0, 4.0, -2.0])

    first = backtest.regression_metrics(actual, predictions, seed=42)
    second = backtest.regression_metrics(actual, predictions, seed=42)

    assert first["rows"] == 4
    assert first["mae"] == pytest.approx(1.25)
    assert first["rmse"] == pytest.approx(1.5)
    assert first["mae_95ci"] == second["mae_95ci"]
    assert first["rmse_95ci"] == second["rmse_95ci"]
    assert len(first["calibration"]["bins"]) > 0


def test_numpy_metrics_match_sklearn_tie_out():
    # dev-only tie-out (sklearn is a test-only dependency, never imported by
    # mlb_research.backtest itself): the numpy reimplementation must match
    # sklearn's reference formulas, not just internal hand-fixtures.
    pytest.importorskip("sklearn")
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, brier_score_loss, log_loss

    rng = np.random.default_rng(0)
    # Genuine Bernoulli draws from the stated probabilities -- realistic,
    # non-separable calibration data (unlike labels constructed to follow
    # the probabilities almost exactly, which drives an unregularized MLE
    # toward an infinite slope and isn't representative of real model output).
    probabilities = rng.uniform(0.1, 0.9, size=500)
    y = (rng.uniform(size=500) < probabilities).astype(int)

    metrics = backtest.classification_metrics(y, probabilities, seed=1)
    assert metrics["log_loss"] == pytest.approx(log_loss(y, probabilities, labels=[0, 1]), abs=1e-6)
    assert metrics["brier"] == pytest.approx(brier_score_loss(y, probabilities), abs=1e-6)
    assert metrics["accuracy"] == pytest.approx(accuracy_score(y, probabilities >= 0.5), abs=1e-6)

    clipped = np.clip(probabilities, 1e-6, 1 - 1e-6)
    sk_model = LogisticRegression(C=1_000_000, fit_intercept=True, max_iter=1_000).fit(
        np.log(clipped / (1 - clipped)).reshape(-1, 1), y
    )
    calibration = backtest.calibration(y, probabilities)
    assert calibration["intercept"] == pytest.approx(float(sk_model.intercept_[0]), abs=1e-3)
    assert calibration["slope"] == pytest.approx(float(sk_model.coef_[0][0]), abs=1e-3)


def test_aggregate_regression_metrics_weighted_by_rows():
    fold_results = {
        "season-2016": {"rows": 10, "mae": 2.0, "rmse": 3.0},
        "season-2017": {"rows": 30, "mae": 4.0, "rmse": 5.0},
    }
    agg = backtest.aggregate_regression_metrics(fold_results)
    assert agg["rows"] == 40
    # mae = (10 * 2.0 + 30 * 4.0) / 40 = 140 / 40 = 3.5
    assert agg["mae"] == pytest.approx(3.5)
    # rmse = (10 * 3.0 + 30 * 5.0) / 40 = 180 / 40 = 4.5
    assert agg["rmse"] == pytest.approx(4.5)


def test_run_backtest_returns_per_fold_and_aggregate_metrics():
    frame = pd.DataFrame(
        {
            "season": [2014, 2014, 2015, 2015, 2016, 2016, 2017, 2017],
            "cutoff": [2014, 2014, 2015, 2015, 2016, 2016, 2017, 2017],
            "value": [1.0, 3.0, 2.0, 4.0, 5.0, 7.0, 6.0, 8.0],
        }
    )
    folds = backtest.time_ordered_folds((2016, 2017))

    def fit_fn(train):
        return train["value"].mean()

    def predict_fn(model, test):
        return np.full(len(test), model)

    result = backtest.run_backtest(
        frame,
        folds,
        fit_fn,
        predict_fn,
        task="regression",
        time_col="cutoff",
        period_col="season",
        label_col="value",
        feature_cols=("value",),
        seed=0,
    )

    assert set(result.folds) == {"season-2016", "season-2017"}
    assert result.folds["season-2016"].metrics["rows"] == 2
    assert result.folds["season-2017"].metrics["rows"] == 2
    assert result.folds["season-2016"].train_rows == 4
    assert result.folds["season-2016"].test_rows == 2
    assert result.folds["season-2017"].train_rows == 6
    assert result.folds["season-2017"].test_rows == 2
    # train mean of the 2014-2015 rows (1, 3, 2, 4) is 2.5, broadcast to
    # both 2016 test rows.
    assert list(result.folds["season-2016"].predictions) == [2.5, 2.5]
    # summed across the two folds' test rows (2 + 2), not the whole frame.
    assert result.aggregate["rows"] == 4
    assert result.fold_plan == [
        {"name": "season-2016", "train_through": 2015, "test": 2016},
        {"name": "season-2017", "train_through": 2016, "test": 2017},
    ]
    assert result.coverage["snapshot_rows"] == 8
    assert result.coverage["common_rows"] == 8
    assert result.coverage["excluded_rows"] == 0
    assert result.seed == 0


def test_paired_comparison_scores_only_intersecting_keys():
    # model A scored g1/g2/g3, model B scored g2/g4 -- only g2 overlaps.
    pred_a = np.array([0.6, 0.7, 0.8])
    keys_a = ["g1", "g2", "g3"]
    y = np.array([1, 0, 1])  # aligned to keys_a
    pred_b = np.array([0.55, 0.75])
    keys_b = ["g2", "g4"]

    result = backtest.paired_comparison(pred_a, pred_b, y, keys_a, keys_b)

    assert result["count"] == 1
    assert list(result["keys"]) == ["g2"]
    assert result["y"].tolist() == [0]
    assert result["pred_a"].tolist() == [0.7]
    assert result["pred_b"].tolist() == [0.55]

    with pytest.raises(ValueError, match="no common keys"):
        backtest.paired_comparison(pred_a, np.array([0.5]), y, keys_a, ["g99"])


def test_run_backtest_delivers_test_rows_in_time_col_order_for_sequential_models():
    # Rows are shuffled in the input frame. A stateful predict_fn (the shape
    # Elo v2 needs) predicts from its running state *before* folding each
    # row's own outcome in -- that's leak-free only if the harness hands it
    # test rows in time_col order, not frame order.
    frame = pd.DataFrame(
        {
            "season": [2015, 2016, 2016, 2016],
            "cutoff": [2015.0, 2016.3, 2016.1, 2016.2],
            "value": [10.0, 30.0, 10.0, 20.0],
        }
    )
    fold = backtest.Fold("season-2016", 2015, 2016)
    seen_order = []

    def fit_fn(train):
        return {"mean": train["value"].mean(), "count": len(train)}

    def predict_fn(state, test):
        predictions = []
        mean, count = state["mean"], state["count"]
        for _, row in test.iterrows():  # no sort here -- the harness must supply order
            seen_order.append(row["cutoff"])
            predictions.append(mean)  # predict *before* this row updates state
            mean = (mean * count + row["value"]) / (count + 1)
            count += 1
        return predictions

    result = backtest.run_backtest(
        frame,
        [fold],
        fit_fn,
        predict_fn,
        task="regression",
        time_col="cutoff",
        period_col="season",
        label_col="value",
        feature_cols=("value",),
        seed=0,
    )

    assert seen_order == [2016.1, 2016.2, 2016.3]
    # Hand roll: train mean = 10.0 (only the 2015 row), count = 1.
    # cutoff=1 (value=10): predicts 10.0,     then mean = (10*1+10)/2 = 10.0,      count=2
    # cutoff=2 (value=20): predicts 10.0,     then mean = (10.0*2+20)/3 = 13.3333, count=3
    # cutoff=3 (value=30): predicts 13.3333
    assert result.folds["season-2016"].metrics["mae"] == pytest.approx(
        (abs(10 - 10.0) + abs(20 - 10.0) + abs(30 - 13.333333333333334)) / 3
    )


def test_module_imports_without_sklearn_or_xgboost():
    # Run in a clean interpreter: another test in this process may already have
    # imported sklearn/xgboost transitively, which says nothing about what
    # mlb_research.backtest itself pulls in.
    code = (
        "import sys; import mlb_research.backtest; "
        "assert 'sklearn' not in sys.modules, 'backtest imported sklearn'; "
        "assert 'xgboost' not in sys.modules, 'backtest imported xgboost'"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
