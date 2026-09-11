from datetime import UTC, date, datetime

import numpy as np
import pytest

from mlb_baseball.model import experiment


def test_calendar_folds_are_strictly_ordered():
    # experiment.folds() is a thin adapter over mlb_research.backtest
    # .time_ordered_folds() (one implementation of the fold-boundary math);
    # this covers its own contract -- translating back to experiment.Fold's
    # train_through_season/test_season shape and ExperimentError. The
    # underlying math itself is covered by
    # packages/mlb-research/tests/test_backtest.py.
    assert experiment.folds((2016, 2017)) == (
        experiment.Fold("season-2016", 2015, 2016),
        experiment.Fold("season-2017", 2016, 2017),
    )
    with pytest.raises(experiment.ExperimentError, match="unique, sorted"):
        experiment.folds((2017, 2016))


# test_probability_metrics_match_hand_calculation_and_are_deterministic,
# test_regression_metrics_match_hand_calculation_and_are_deterministic, and
# test_aggregate_regression_metrics_weighted_by_rows moved to
# packages/mlb-research/tests/test_backtest.py: experiment._metrics /
# _regression_metrics / _aggregate_regression_metrics are now direct
# re-exports of mlb_research.backtest's classification_metrics /
# regression_metrics / aggregate_regression_metrics, so the hand-fixture
# coverage there is coverage here too -- one definition, one test.


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
        "gam_regressor",
        "svm_regressor",
        "bayesian_regressor",
        "neural_regressor",
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

    experiment._validate_parameters("gam", {"max_iter": 50})
    with pytest.raises(experiment.ExperimentError, match="unsupported parameter"):
        experiment._validate_parameters("gam", {"bad_param": 1})

    experiment._validate_parameters("gam_regressor", {"alpha": 0.5})
    with pytest.raises(experiment.ExperimentError, match="unsupported parameter"):
        experiment._validate_parameters("gam_regressor", {"bad_param": 1})

    experiment._validate_parameters("svm", {"kernel": "linear"})
    with pytest.raises(experiment.ExperimentError, match="unsupported parameter"):
        experiment._validate_parameters("svm", {"bad_param": 1})

    experiment._validate_parameters("svm_regressor", {"kernel": "linear"})
    with pytest.raises(experiment.ExperimentError, match="unsupported parameter"):
        experiment._validate_parameters("svm_regressor", {"bad_param": 1})

    experiment._validate_parameters("bayesian", {"var_smoothing": 1e-8})
    with pytest.raises(experiment.ExperimentError, match="unsupported parameter"):
        experiment._validate_parameters("bayesian", {"bad_param": 1})

    experiment._validate_parameters("bayesian_regressor", {"alpha_1": 1e-5})
    with pytest.raises(experiment.ExperimentError, match="unsupported parameter"):
        experiment._validate_parameters("bayesian_regressor", {"bad_param": 1})

    experiment._validate_parameters("neural", {"hidden_layer_sizes": (50,)})
    with pytest.raises(experiment.ExperimentError, match="unsupported parameter"):
        experiment._validate_parameters("neural", {"bad_param": 1})

    experiment._validate_parameters("neural_regressor", {"hidden_layer_sizes": (50,)})
    with pytest.raises(experiment.ExperimentError, match="unsupported parameter"):
        experiment._validate_parameters("neural_regressor", {"bad_param": 1})


def test_validate_parameters_rejects_svm_probability_false():
    # Real bug found via PR review: "probability" is a genuine SVC
    # constructor parameter, so the generic allowed-set check alone lets
    # {"probability": False} through -- but _probabilities() unconditionally
    # calls predict_proba(), which SVC only exposes when probability=True.
    # Without this explicit rejection, a caller-configured, individually
    # "valid" SVC would fail later, mid-run, during scoring instead of at
    # validation time.
    with pytest.raises(experiment.ExperimentError, match="probability=True"):
        experiment._validate_parameters("svm", {"probability": False})
    # An explicit probability=True override is redundant but not harmful --
    # confirm it's still accepted, not incorrectly rejected too.
    experiment._validate_parameters("svm", {"probability": True})
    # svm_regressor is unaffected -- SVR has no probability parameter at all.
    with pytest.raises(experiment.ExperimentError, match="unsupported parameter"):
        experiment._validate_parameters("svm_regressor", {"probability": False})


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


def test_evaluation_frame_has_the_expected_shape():
    values: dict[str, float | None] = {"home_wins": 5.0, "home_win_pct": 0.55}
    row_a = experiment.SnapshotRow(
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
        values,
        True,
    )
    row_b = experiment.SnapshotRow(
        "k2",
        "pk2",
        datetime(2024, 4, 2, 12, 0, tzinfo=UTC),
        2024,
        date(2024, 4, 2),
        1,
        1,
        2,
        4,
        6,
        values,
        True,
    )
    spec = experiment.TARGET_REGISTRY["home_win"]

    frame = experiment._evaluation_frame([row_a, row_b], spec)

    # Identity/period/cutoff/outcome columns, BASE_COLUMNS + LOG5_COLUMNS
    # (log5 reads home_win_pct/away_win_pct directly, not via BASE_COLUMNS;
    # elo needs the team ids and scores), then the label -- this is the
    # exact frame shape run_backtest scores.
    assert list(frame.columns) == [
        "game_instance_key",
        "season",
        "feature_cutoff_at",
        "home_team_id",
        "away_team_id",
        "home_score",
        "away_score",
        "home_win",
        *experiment.BASE_COLUMNS,
        *experiment.LOG5_COLUMNS,
        "label",
    ]
    assert len(frame) == 2
    assert list(frame["game_instance_key"]) == ["k1", "k2"]
    assert list(frame["season"]) == [2024, 2024]
    assert list(frame["home_team_id"]) == [1, 1]
    assert list(frame["away_team_id"]) == [2, 2]
    assert list(frame["home_score"]) == [5, 4]
    assert list(frame["away_score"]) == [3, 6]
    assert list(frame["home_win"]) == [True, True]
    assert list(frame["label"]) == [1.0, 1.0]
    assert list(frame["home_wins"]) == [5.0, 5.0]
    assert list(frame["home_win_pct"]) == [0.55, 0.55]
    # home_rest isn't set on either row -- .values.get() leaves it missing
    # rather than fabricating a zero.
    assert frame["home_rest"].isna().all()


def _estimator_factory_fixture_rows() -> list[experiment.SnapshotRow]:
    # 3 train rows (season 2015) + 3 test rows (season 2016), distinct team
    # pairs each game so elo's ratings actually move, every BASE_COLUMNS +
    # LOG5_COLUMNS value populated so both target specs' required_columns
    # are satisfied.
    def row(
        key: str,
        day: int,
        season: int,
        home_team: int,
        away_team: int,
        home_score: int,
        away_score: int,
        home_win: bool,
        offset: float,
    ) -> experiment.SnapshotRow:
        values: dict[str, float | None] = {
            "home_wins": 10.0 + offset,
            "home_losses": 5.0,
            "away_wins": 8.0,
            "away_losses": 7.0,
            "home_runs_for": 40.0 + offset,
            "home_runs_allowed": 35.0,
            "away_runs_for": 38.0,
            "away_runs_allowed": 36.0,
            "home_rest": 1.0,
            "away_rest": 1.0,
            "home_field": 1.0,
            "home_win_pct": 0.6,
            "away_win_pct": 0.5,
        }
        return experiment.SnapshotRow(
            key,
            f"pk-{key}",
            datetime(season, 4, day, 12, 0, tzinfo=UTC),
            season,
            date(season, 4, day),
            1,
            home_team,
            away_team,
            home_score,
            away_score,
            values,
            home_win,
        )

    return [
        row("k1", 1, 2015, 1, 2, 5, 3, True, 0.0),
        row("k2", 2, 2015, 3, 4, 2, 6, False, 1.0),
        row("k3", 3, 2015, 2, 1, 7, 1, True, 2.0),
        row("k4", 1, 2016, 1, 3, 4, 3, True, 3.0),
        row("k5", 2, 2016, 2, 4, 6, 2, True, 4.0),
        row("k6", 3, 2016, 4, 1, 3, 5, False, 5.0),
    ]


def _split_factory_fixture(
    spec: experiment.TargetSpec,
) -> tuple[list[experiment.SnapshotRow], list[experiment.SnapshotRow], object, object]:
    rows = _estimator_factory_fixture_rows()
    train_rows, test_rows = rows[:3], rows[3:]
    frame = experiment._evaluation_frame(rows, spec)
    train_frame = frame[frame["season"] <= 2015].sort_values("feature_cutoff_at")
    test_frame = frame[frame["season"] == 2016].sort_values("feature_cutoff_at")
    return train_rows, test_rows, train_frame, test_frame


_CLASSIFICATION_FAMILIES = (
    "home_rate",
    "log5",
    "elo",
    "logistic",
    "hist_gradient_boosting",
    "xgboost",
    "random_forest",
    "extra_trees",
    "gam",
    "svm",
    "bayesian",
    "neural",
)
_REGRESSION_FAMILIES = (
    "zero",
    "season_average",
    "ridge",
    "hist_gradient_boosting_regressor",
    "xgboost_regressor",
    "random_forest_regressor",
    "extra_trees_regressor",
    "gam_regressor",
    "svm_regressor",
    "bayesian_regressor",
    "neural_regressor",
)


# Captured once from experiment._probabilities/_predictions (the pre-slice-2
# SnapshotRow-based implementation, byte-for-byte the same math this
# fixture's _estimator_factory output is now checked against) before those
# functions were deleted as dead code (task 5.6) -- pins the exact numeric
# output per family rather than re-deriving it from code this test would
# then be comparing against itself.
_EXPECTED_CLASSIFICATION_PREDICTIONS = {
    "home_rate": [0.6666666667, 0.6666666667, 0.6666666667],
    "log5": [0.6, 0.6, 0.6],
    "elo": [0.5353566039, 0.5336110744, 0.5338020016],
    "logistic": [0.6666684457, 0.6666684457, 0.6666684457],
    "hist_gradient_boosting": [0.6666666667, 0.6666666667, 0.6666666667],
    "xgboost": [0.6666666865, 0.6666666865, 0.6666666865],
    "random_forest": [0.73, 0.73, 0.73],
    "extra_trees": [1.0, 1.0, 1.0],
    "gam": [0.9130932256, 0.9130932256, 0.9130932256],
    "svm": [0.3913451218, 0.4289719063, 0.4294128993],
    "bayesian": [1.0, 1.0, 1.0],
    "neural": [0.999995193, 0.9999999968, 1.0],
}
_EXPECTED_REGRESSION_PREDICTIONS = {
    "zero": [0.0, 0.0, 0.0],
    "season_average": [0.3111111111, 0.3403508772, 0.3666666667],
    "ridge": [4.7619047619, 6.4761904762, 8.1904761905],
    "hist_gradient_boosting_regressor": [1.3333333333, 1.3333333333, 1.3333333333],
    "xgboost_regressor": [5.6289200783, 5.6289200783, 5.6289200783],
    "random_forest_regressor": [3.12, 3.12, 3.12],
    "extra_trees_regressor": [6.0, 6.0, 6.0],
    "gam_regressor": [5.7619047619, 5.7619047619, 5.7619047619],
    "svm_regressor": [2.4413028222, 2.2231287955, 2.2206527852],
    "bayesian_regressor": [1.3379647009, 1.3402803847, 1.3425960685],
    "neural_regressor": [14.0945376978, 21.4599101866, 28.8230956418],
}


@pytest.mark.parametrize("model_family", _CLASSIFICATION_FAMILIES)
def test_estimator_factory_matches_probabilities_on_a_fixed_fixture(model_family):
    spec = experiment.TARGET_REGISTRY["home_win"]
    config = experiment.ExperimentConfig(snapshot_id="s", model_family=model_family, seed=0)

    _, _, train_frame, test_frame = _split_factory_fixture(spec)
    fit_fn, predict_fn = experiment._estimator_factory(config, spec)
    actual = predict_fn(fit_fn(train_frame), test_frame)

    assert np.allclose(actual, _EXPECTED_CLASSIFICATION_PREDICTIONS[model_family], atol=1e-9)


@pytest.mark.parametrize("model_family", _REGRESSION_FAMILIES)
def test_estimator_factory_matches_predictions_on_a_fixed_fixture(model_family):
    spec = experiment.TARGET_REGISTRY["run_differential"]
    config = experiment.ExperimentConfig(snapshot_id="s", model_family=model_family, seed=0)

    _, _, train_frame, test_frame = _split_factory_fixture(spec)
    fit_fn, predict_fn = experiment._estimator_factory(config, spec)
    actual = predict_fn(fit_fn(train_frame), test_frame)

    assert np.allclose(actual, _EXPECTED_REGRESSION_PREDICTIONS[model_family], atol=1e-9)


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
        "gam",
        "gam_regressor",
        "svm",
        "neural",
        "neural_regressor",
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


def test_make_estimator_lets_a_valid_svm_regressor_override_take_effect():
    # svm_regressor is excluded from the parametrized override test above:
    # unlike every other family here, scikit-learn's SVR has no
    # random_state constructor parameter at all (SVR's solver is
    # deterministic, unlike SVC's probability-calibration step) -- passing
    # one would raise TypeError, not silently ignore it. Covers the same
    # "an explicit, valid override actually takes effect" contract with a
    # parameter SVR does support.
    estimator = experiment._make_estimator("svm_regressor", {"C": 2.5}, seed=0)
    model = estimator.named_steps["model"]
    assert model.C == 2.5


def test_make_estimator_lets_a_valid_bayesian_override_take_effect():
    # bayesian (GaussianNB) and bayesian_regressor (BayesianRidge) are both
    # excluded from the random_state parametrized test above: neither
    # estimator has a random_state constructor parameter at all -- both fit
    # deterministically (GaussianNB via a single closed-form per-class
    # calculation, BayesianRidge via deterministic iterative evidence
    # maximization), unlike every other family in this file. Covers the
    # same "an explicit, valid override actually takes effect" contract
    # with parameters they do support.
    estimator = experiment._make_estimator("bayesian", {"var_smoothing": 1e-7}, seed=0)
    model = estimator.named_steps["model"]
    assert model.var_smoothing == 1e-7


def test_make_estimator_lets_a_valid_bayesian_regressor_override_take_effect():
    estimator = experiment._make_estimator("bayesian_regressor", {"alpha_1": 1e-5}, seed=0)
    model = estimator.named_steps["model"]
    assert model.alpha_1 == 1e-5


def test_make_estimator_lets_a_valid_neural_hidden_layer_override_take_effect():
    # PR #35 review: the parametrized random_state override test above
    # proves *some* override reaches MLPClassifier/MLPRegressor, but
    # hidden_layer_sizes -- the parameter that actually distinguishes
    # "neural" from every other family in this file -- was never itself
    # checked end to end. Covers the same "an explicit, valid override
    # actually takes effect" contract with the parameter unique to this
    # family.
    estimator = experiment._make_estimator("neural", {"hidden_layer_sizes": (50,)}, seed=0)
    model = estimator.named_steps["model"]
    assert model.hidden_layer_sizes == (50,)

    estimator = experiment._make_estimator(
        "neural_regressor", {"hidden_layer_sizes": (50,)}, seed=0
    )
    model = estimator.named_steps["model"]
    assert model.hidden_layer_sizes == (50,)
