import math
from datetime import UTC, date, datetime

import numpy as np
import pytest

from mlb_baseball.model import experiment


def test_calendar_folds_are_strictly_ordered():
    assert experiment.folds((2016, 2017)) == (
        experiment.Fold("season-2016", 2015, 2016),
        experiment.Fold("season-2017", 2016, 2017),
    )
    with pytest.raises(experiment.ExperimentError, match="unique, sorted"):
        experiment.folds((2017, 2016))


def test_probability_metrics_match_hand_calculation_and_are_deterministic():
    actual = np.array([1, 0])
    probabilities = np.array([0.75, 0.25])

    first = experiment._metrics(actual, probabilities, seed=7)
    second = experiment._metrics(actual, probabilities, seed=7)

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


def test_target_registry_specifications():
    assert set(experiment.TARGET_REGISTRY) == {"home_win", "run_differential"}

    hw_spec = experiment.TARGET_REGISTRY["home_win"]
    assert hw_spec.name == "home_win"
    assert hw_spec.task_type == "classification"
    assert hw_spec.required_columns == ("home_win_pct", "away_win_pct")
    assert hw_spec.valid_model_families == experiment.SUPPORTED_MODELS

    rd_spec = experiment.TARGET_REGISTRY["run_differential"]
    assert rd_spec.name == "run_differential"
    assert rd_spec.task_type == "regression"
    assert rd_spec.required_columns == (
        "home_runs_for",
        "home_runs_allowed",
        "away_runs_for",
        "away_runs_allowed",
        "home_wins",
        "home_losses",
        "away_wins",
        "away_losses",
    )
    assert rd_spec.valid_model_families == (
        "zero",
        "season_average",
        "ridge",
        "hist_gradient_boosting_regressor",
        "xgboost_regressor",
        "random_forest_regressor",
        "extra_trees_regressor",
    )

    sample_row = experiment.SnapshotRow(
        game_instance_key="key-1",
        mlb_game_pk="pk-1",
        feature_cutoff_at=datetime(2024, 4, 1, 12, 0, tzinfo=UTC),
        season=2024,
        game_date=date(2024, 4, 1),
        game_number=1,
        home_team_id=1,
        away_team_id=2,
        home_score=7,
        away_score=4,
        values={},
        home_win=True,
    )
    assert hw_spec.label(sample_row) == 1.0
    assert rd_spec.label(sample_row) == 3.0


def test_regression_metrics_match_hand_calculation_and_are_deterministic():
    # Hand-computed test vectors:
    # actual:      [3.0, -1.0, 4.0,  0.0]
    # predictions: [2.0,  1.0, 4.0, -2.0]
    # errors (act - pred): [1.0, -2.0, 0.0, 2.0]
    # abs errors: [1.0, 2.0, 0.0, 2.0] -> MAE = (1 + 2 + 0 + 2) / 4 = 1.25
    # sq errors:  [1.0, 4.0, 0.0, 4.0] -> MSE = (1 + 4 + 0 + 4) / 4 = 2.25 -> RMSE = 1.5
    actual = np.array([3.0, -1.0, 4.0, 0.0])
    predictions = np.array([2.0, 1.0, 4.0, -2.0])

    first = experiment._regression_metrics(actual, predictions, seed=42)
    second = experiment._regression_metrics(actual, predictions, seed=42)

    assert first["rows"] == 4
    assert first["mae"] == pytest.approx(1.25)
    assert first["rmse"] == pytest.approx(1.5)
    assert first["mae_95ci"] == second["mae_95ci"]
    assert first["rmse_95ci"] == second["rmse_95ci"]
    assert len(first["calibration"]["bins"]) > 0


def test_aggregate_regression_metrics_weighted_by_rows():
    fold_results = {
        "season-2016": {"rows": 10, "mae": 2.0, "rmse": 3.0},
        "season-2017": {"rows": 30, "mae": 4.0, "rmse": 5.0},
    }
    agg = experiment._aggregate_regression_metrics(fold_results)
    assert agg["rows"] == 40
    # mae = (10 * 2.0 + 30 * 4.0) / 40 = 140 / 40 = 3.5
    assert agg["mae"] == pytest.approx(3.5)
    # rmse = (10 * 3.0 + 30 * 5.0) / 40 = 180 / 40 = 4.5
    assert agg["rmse"] == pytest.approx(4.5)


def test_validate_parameters_for_all_model_families():
    # Baselines accept no parameters
    for model_family in ("home_rate", "log5", "elo", "zero", "season_average"):
        experiment._validate_parameters(model_family, {})
        with pytest.raises(experiment.ExperimentError, match="accepts no estimator parameters"):
            experiment._validate_parameters(model_family, {"alpha": 1.0})

    # Regressors validate parameters
    experiment._validate_parameters("ridge", {"alpha": 0.5})
    with pytest.raises(experiment.ExperimentError, match="unsupported parameter"):
        experiment._validate_parameters("ridge", {"invalid_param": 1})

    experiment._validate_parameters("hist_gradient_boosting_regressor", {"max_iter": 50})
    with pytest.raises(experiment.ExperimentError, match="unsupported parameter"):
        experiment._validate_parameters("hist_gradient_boosting_regressor", {"bad_param": 1})

    experiment._validate_parameters("xgboost_regressor", {"n_estimators": 50})
    with pytest.raises(experiment.ExperimentError, match="unsupported parameter"):
        experiment._validate_parameters("xgboost_regressor", {"bad_param": 1})

    experiment._validate_parameters("random_forest", {"max_depth": 5})
    with pytest.raises(experiment.ExperimentError, match="unsupported parameter"):
        experiment._validate_parameters("random_forest", {"bad_param": 1})

    experiment._validate_parameters("extra_trees", {"max_depth": 5})
    with pytest.raises(experiment.ExperimentError, match="unsupported parameter"):
        experiment._validate_parameters("extra_trees", {"bad_param": 1})

    experiment._validate_parameters("random_forest_regressor", {"max_depth": 5})
    with pytest.raises(experiment.ExperimentError, match="unsupported parameter"):
        experiment._validate_parameters("random_forest_regressor", {"bad_param": 1})

    experiment._validate_parameters("extra_trees_regressor", {"max_depth": 5})
    with pytest.raises(experiment.ExperimentError, match="unsupported parameter"):
        experiment._validate_parameters("extra_trees_regressor", {"bad_param": 1})


def test_common_rows_filters_per_target_spec():
    base_values: dict[str, float | None] = {
        "home_win_pct": 0.55,
        "away_win_pct": 0.45,
        "home_runs_for": 20.0,
        "home_runs_allowed": 15.0,
        "away_runs_for": 18.0,
        "away_runs_allowed": 22.0,
        "home_wins": 5.0,
        "home_losses": 3.0,
        "away_wins": 4.0,
        "away_losses": 5.0,
    }
    row_full = experiment.SnapshotRow(
        "k1",
        "pk1",
        datetime(2024, 4, 1, 12, 0, tzinfo=UTC),
        2024,
        date(2024, 4, 1),
        1,
        1,
        2,
        5,
        3,
        base_values,
        True,
    )
    # Missing rate inputs for home_win
    values_no_rates = dict(base_values, home_win_pct=None, away_win_pct=None)
    row_no_rates = experiment.SnapshotRow(
        "k2",
        "pk2",
        datetime(2024, 4, 1, 12, 0, tzinfo=UTC),
        2024,
        date(2024, 4, 1),
        1,
        1,
        2,
        5,
        3,
        values_no_rates,
        True,
    )
    # Missing runs for run_differential
    values_no_runs = dict(base_values, home_runs_for=None)
    row_no_runs = experiment.SnapshotRow(
        "k3",
        "pk3",
        datetime(2024, 4, 1, 12, 0, tzinfo=UTC),
        2024,
        date(2024, 4, 1),
        1,
        1,
        2,
        5,
        3,
        values_no_runs,
        True,
    )

    hw_spec = experiment.TARGET_REGISTRY["home_win"]
    rd_spec = experiment.TARGET_REGISTRY["run_differential"]

    # home_win keeps row_full and row_no_runs (which has win_pct), drops row_no_rates
    hw_filtered = experiment._common_rows([row_full, row_no_rates, row_no_runs], hw_spec)
    assert [r.game_instance_key for r in hw_filtered] == ["k1", "k3"]

    # run_differential keeps row_full and row_no_rates (which has runs/wins), drops row_no_runs
    rd_filtered = experiment._common_rows([row_full, row_no_rates, row_no_runs], rd_spec)
    assert [r.game_instance_key for r in rd_filtered] == ["k1", "k2"]


@pytest.mark.parametrize(
    "model_family",
    [
        "logistic",
        "hist_gradient_boosting",
        "xgboost",
        "random_forest",
        "extra_trees",
        "ridge",
        "hist_gradient_boosting_regressor",
        "xgboost_regressor",
        "random_forest_regressor",
        "extra_trees_regressor",
    ],
)
def test_make_estimator_lets_a_valid_override_actually_take_effect(model_family):
    # Real bug found via PR review: every one of these families passes its
    # own fixed defaults (random_state=seed, and for the ensembles
    # n_estimators/n_jobs too) as explicit keyword arguments *and* expands
    # `parameters` alongside them -- a caller overriding any of those (which
    # _validate_parameters legitimately allows, since scikit-learn exposes
    # all of them as real constructor params) previously raised "got
    # multiple values for keyword argument" instead of applying the
    # override, for every model family in this file, not just the ones
    # this test happens to be checking. Constructing with an override must
    # not raise, and the resulting estimator must actually reflect it.
    estimator = experiment._make_estimator(model_family, {"random_state": 99}, seed=0)
    model = estimator.named_steps["model"] if hasattr(estimator, "named_steps") else estimator
    assert model.random_state == 99
