"""Unit tests for Stage 3 forward-stepwise feature selection logic."""

from dataclasses import asdict
from datetime import date, datetime
from unittest.mock import MagicMock

import numpy as np
import pytest
from sklearn.metrics import log_loss, mean_absolute_error

from mlb_baseball.model.experiment import (
    BASE_COLUMNS,
    ExperimentError,
    Fold,
    SnapshotRow,
    _make_estimator,
)
from mlb_baseball.model.feature_select_stepwise import (
    _named_matrix,
    _selection_id,
    select_features_stepwise,
)


def _make_dummy_row(
    values: dict[str, float | None], season: int = 2016, outcome: bool = True
) -> SnapshotRow:
    return SnapshotRow(
        game_instance_key="mlb:123",
        mlb_game_pk="123",
        feature_cutoff_at=datetime(season, 4, 1, 12, 0),
        season=season,
        game_date=date(season, 4, 1),
        game_number=1,
        home_team_id=1,
        away_team_id=2,
        home_score=5,
        away_score=3,
        values=values,
        home_win=outcome,
    )


def test_named_matrix_extraction():
    row1 = _make_dummy_row({"home_wins": 5.0, "away_wins": 3.0, "home_losses": None})
    row2 = _make_dummy_row({"home_wins": 2.0, "away_wins": 4.0, "home_losses": 1.0})

    # Subsetting specific columns
    mat = _named_matrix([row1, row2], ["home_wins", "away_wins"])
    assert mat.shape == (2, 2)
    assert np.allclose(mat, [[5.0, 3.0], [2.0, 4.0]])

    # Handling None as NaN
    mat_with_null = _named_matrix([row1, row2], ["home_wins", "home_losses"])
    assert mat_with_null.shape == (2, 2)
    assert mat_with_null[0, 0] == 5.0
    assert np.isnan(mat_with_null[0, 1])
    assert mat_with_null[1, 0] == 2.0
    assert mat_with_null[1, 1] == 1.0

    # Empty column list returns empty 2D array
    mat_empty = _named_matrix([row1, row2], [])
    assert mat_empty.shape == (2, 0)


def test_selection_id_is_deterministic():
    folds = [asdict(Fold("season-2020", 2019, 2020)), asdict(Fold("season-2021", 2020, 2021))]
    id1 = _selection_id("snap-1", "home_win", folds, min_survival_fraction=0.70, seed=42)
    id2 = _selection_id("snap-1", "home_win", folds, min_survival_fraction=0.70, seed=42)
    assert id1 == id2
    assert id1.startswith("fstep-")

    id_diff_seed = _selection_id("snap-1", "home_win", folds, min_survival_fraction=0.70, seed=43)
    assert id1 != id_diff_seed

    id_diff_target = _selection_id(
        "snap-1", "run_differential", folds, min_survival_fraction=0.70, seed=42
    )
    assert id1 != id_diff_target

    id_diff_thresh = _selection_id("snap-1", "home_win", folds, min_survival_fraction=0.50, seed=42)
    assert id1 != id_diff_thresh


def test_empty_candidate_set_raises_experiment_error(monkeypatch):
    conn = MagicMock()
    # Mock snapshot metadata
    monkeypatch.setattr(
        "mlb_baseball.model.feature_select_stepwise._snapshot_metadata",
        lambda _c, _s: ("home_win", "game_base_v1", "local_research"),
    )
    # Mock select_features to return all 0 survivors
    monkeypatch.setattr(
        "mlb_baseball.model.feature_select_stepwise.select_features",
        lambda _c, _s, **_kw: {
            "selection_id": "fsel-mock",
            "total_folds_evaluated": 5,
            "features": {col: {"both_stages_survived_folds": 0} for col in BASE_COLUMNS},
        },
    )

    with pytest.raises(
        ExperimentError,
        match="no candidate features survived stage 1\\+2 at the 70th-percent threshold",
    ):
        select_features_stepwise(conn, "snap-mock", min_survival_fraction=0.70)


def test_synthetic_classification_paired_shuffled_comparison_separates_signal_from_noise():
    """Prove that probe logistic baseline with paired real-vs-shuffled comparison
    reliably identifies an informative signal and gives it a large improvement margin.
    """
    n_train = 500
    n_val = 200
    seeds = [0, 1, 2, 3, 4]
    informative_passed = 0
    signal_margins = []
    noise_margins = []

    for seed in seeds:
        rng = np.random.default_rng(seed)
        x_signal_train = rng.standard_normal(n_train)
        x_noise_train = rng.standard_normal(n_train)
        prob_train = 1 / (1 + np.exp(-(2.5 * x_signal_train + 0.2 * rng.standard_normal(n_train))))
        y_train = (prob_train >= 0.5).astype(np.int64)

        x_signal_val = rng.standard_normal(n_val)
        x_noise_val = rng.standard_normal(n_val)
        prob_val = 1 / (1 + np.exp(-(2.5 * x_signal_val + 0.2 * rng.standard_normal(n_val))))
        y_val = (prob_val >= 0.5).astype(np.int64)

        # Signal feature
        clf_real = _make_estimator("logistic", {}, seed)
        clf_real.fit(x_signal_train.reshape(-1, 1), y_train)
        probs_real = clf_real.predict_proba(x_signal_val.reshape(-1, 1))[:, 1]
        real_loss_signal = float(log_loss(y_val, probs_real, labels=[0, 1]))

        clf_shuffled = _make_estimator("logistic", {}, seed)
        shuffled_signal_train = rng.permutation(x_signal_train)
        clf_shuffled.fit(shuffled_signal_train.reshape(-1, 1), y_train)
        probs_shuffled = clf_shuffled.predict_proba(x_signal_val.reshape(-1, 1))[:, 1]
        shuffled_loss_signal = float(log_loss(y_val, probs_shuffled, labels=[0, 1]))

        signal_margin = shuffled_loss_signal - real_loss_signal
        signal_margins.append(signal_margin)
        if real_loss_signal < shuffled_loss_signal:
            informative_passed += 1

        # Noise feature
        clf_real_noise = _make_estimator("logistic", {}, seed)
        clf_real_noise.fit(x_noise_train.reshape(-1, 1), y_train)
        probs_real_noise = clf_real_noise.predict_proba(x_noise_val.reshape(-1, 1))[:, 1]
        real_loss_noise = float(log_loss(y_val, probs_real_noise, labels=[0, 1]))

        clf_shuffled_noise = _make_estimator("logistic", {}, seed)
        shuffled_noise_train = rng.permutation(x_noise_train)
        clf_shuffled_noise.fit(shuffled_noise_train.reshape(-1, 1), y_train)
        probs_shuffled_noise = clf_shuffled_noise.predict_proba(x_noise_val.reshape(-1, 1))[:, 1]
        shuffled_loss_noise = float(log_loss(y_val, probs_shuffled_noise, labels=[0, 1]))

        noise_margin = shuffled_loss_noise - real_loss_noise
        noise_margins.append(noise_margin)

    # Signal feature must consistently beat its shuffled control
    assert informative_passed == 5, f"Informative signal passed: {informative_passed}/5"
    # Signal improvement margin must overwhelmingly exceed noise margin
    assert np.mean(signal_margins) > 0.20
    assert np.mean(signal_margins) > 10 * max(0.0, float(np.mean(noise_margins)))


def test_synthetic_regression_paired_shuffled_comparison_separates_signal_from_noise():
    """Prove that probe ridge baseline with paired real-vs-shuffled comparison
    reliably identifies an informative signal and gives it a large improvement margin.
    """
    n_train = 500
    n_val = 200
    seeds = [0, 1, 2, 3, 4]
    informative_passed = 0
    signal_margins = []
    noise_margins = []

    for seed in seeds:
        rng = np.random.default_rng(seed)
        x_signal_train = rng.standard_normal(n_train)
        x_noise_train = rng.standard_normal(n_train)
        y_train = 3.0 * x_signal_train + rng.standard_normal(n_train)

        x_signal_val = rng.standard_normal(n_val)
        x_noise_val = rng.standard_normal(n_val)
        y_val = 3.0 * x_signal_val + rng.standard_normal(n_val)

        # Signal feature
        reg_real = _make_estimator("ridge", {}, seed)
        reg_real.fit(x_signal_train.reshape(-1, 1), y_train)
        preds_real = reg_real.predict(x_signal_val.reshape(-1, 1))
        real_mae_signal = float(mean_absolute_error(y_val, preds_real))

        reg_shuffled = _make_estimator("ridge", {}, seed)
        shuffled_signal_train = rng.permutation(x_signal_train)
        reg_shuffled.fit(shuffled_signal_train.reshape(-1, 1), y_train)
        preds_shuffled = reg_shuffled.predict(x_signal_val.reshape(-1, 1))
        shuffled_mae_signal = float(mean_absolute_error(y_val, preds_shuffled))

        signal_margin = shuffled_mae_signal - real_mae_signal
        signal_margins.append(signal_margin)
        if real_mae_signal < shuffled_mae_signal:
            informative_passed += 1

        # Noise feature
        reg_real_noise = _make_estimator("ridge", {}, seed)
        reg_real_noise.fit(x_noise_train.reshape(-1, 1), y_train)
        preds_real_noise = reg_real_noise.predict(x_noise_val.reshape(-1, 1))
        real_mae_noise = float(mean_absolute_error(y_val, preds_real_noise))

        reg_shuffled_noise = _make_estimator("ridge", {}, seed)
        shuffled_noise_train = rng.permutation(x_noise_train)
        reg_shuffled_noise.fit(shuffled_noise_train.reshape(-1, 1), y_train)
        preds_shuffled_noise = reg_shuffled_noise.predict(x_noise_val.reshape(-1, 1))
        shuffled_mae_noise = float(mean_absolute_error(y_val, preds_shuffled_noise))

        noise_margin = shuffled_mae_noise - real_mae_noise
        noise_margins.append(noise_margin)

    assert informative_passed == 5, f"Informative signal passed: {informative_passed}/5"
    assert np.mean(signal_margins) > 1.0
    assert np.mean(signal_margins) > 10 * max(0.0, float(np.mean(noise_margins)))
