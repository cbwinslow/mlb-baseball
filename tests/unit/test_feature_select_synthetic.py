"""Unit tests for feature-selection stability report logic."""

from dataclasses import asdict

import numpy as np
from sklearn.inspection import permutation_importance

from mlb_baseball.model.experiment import (
    Fold,
    _make_estimator,
)
from mlb_baseball.model.feature_select import _selection_id


def test_selection_id_is_deterministic():
    folds = [asdict(Fold("season-2020", 2019, 2020)), asdict(Fold("season-2021", 2020, 2021))]
    id1 = _selection_id("snap-1", "home_win", folds, n_repeats=30, seed=42)
    id2 = _selection_id("snap-1", "home_win", folds, n_repeats=30, seed=42)
    assert id1 == id2
    assert id1.startswith("fsel-")

    id_diff_seed = _selection_id("snap-1", "home_win", folds, n_repeats=30, seed=43)
    assert id1 != id_diff_seed

    id_diff_target = _selection_id("snap-1", "run_differential", folds, n_repeats=30, seed=42)
    assert id1 != id_diff_target

    id_diff_repeats = _selection_id("snap-1", "home_win", folds, n_repeats=10, seed=42)
    assert id1 != id_diff_repeats


def test_synthetic_classification_separates_informative_feature_from_noise():
    """Prove that Stage 1 (logistic) and Stage 2 (XGBoost) separate a known

    informative signal from injected noise across random seeds.
    """
    n_samples = 500
    seeds = [0, 1, 2, 3, 4]
    stage1_informative_wins = 0
    stage2_informative_wins = 0
    stage1_noise_wins = 0
    stage2_noise_wins = 0

    for seed in seeds:
        rng = np.random.default_rng(seed)
        # Column 0: informative signal
        x_signal = rng.standard_normal(n_samples)
        # Column 1 & 2: pure noise
        x_noise1 = rng.standard_normal(n_samples)
        x_noise2 = rng.standard_normal(n_samples)
        # Injected control noise column
        x_control_noise = rng.standard_normal(n_samples)

        # Binary label strongly driven by x_signal
        prob = 1 / (1 + np.exp(-(2.5 * x_signal + 0.3 * rng.standard_normal(n_samples))))
        y = (prob >= 0.5).astype(np.int64)

        x_mat = np.column_stack([x_signal, x_noise1, x_noise2, x_control_noise])
        feature_names = ["signal", "noise1", "noise2", "__noise__"]

        # Stage 1: Logistic Regression + Permutation Importance
        clf1 = _make_estimator("logistic", {}, seed)
        clf1.fit(x_mat, y)
        perm1 = permutation_importance(
            clf1, x_mat, y, scoring="neg_log_loss", n_repeats=30, random_state=seed
        )
        imp1 = dict(zip(feature_names, perm1.importances_mean, strict=True))
        noise_imp1 = imp1["__noise__"]

        if imp1["signal"] > noise_imp1:
            stage1_informative_wins += 1
        if imp1["noise1"] > noise_imp1:
            stage1_noise_wins += 1
        if imp1["noise2"] > noise_imp1:
            stage1_noise_wins += 1

        # Stage 2: XGBoost Classifier
        clf2 = _make_estimator("xgboost", {}, seed)
        clf2.fit(x_mat, y)
        imp2 = dict(zip(feature_names, clf2.feature_importances_, strict=True))
        noise_imp2 = imp2["__noise__"]

        if imp2["signal"] > noise_imp2:
            stage2_informative_wins += 1
        if imp2["noise1"] > noise_imp2:
            stage2_noise_wins += 1
        if imp2["noise2"] > noise_imp2:
            stage2_noise_wins += 1

    # Informative feature must reliably beat noise across almost all / all seeds
    assert stage1_informative_wins >= 4, f"Stage 1 informative wins: {stage1_informative_wins}/5"
    assert stage2_informative_wins >= 4, f"Stage 2 informative wins: {stage2_informative_wins}/5"
    # Pure noise features should not reliably beat the control noise threshold
    assert stage1_noise_wins <= 6, f"Stage 1 false positive noise wins: {stage1_noise_wins}/10"
    assert stage2_noise_wins <= 6, f"Stage 2 false positive noise wins: {stage2_noise_wins}/10"


def test_synthetic_regression_separates_informative_feature_from_noise():
    """Prove that Stage 1 (Ridge) and Stage 2 (XGBRegressor) separate a known

    informative signal from injected noise across random seeds.
    """
    n_samples = 500
    seeds = [0, 1, 2, 3, 4]
    stage1_informative_wins = 0
    stage2_informative_wins = 0
    stage1_noise_wins = 0
    stage2_noise_wins = 0

    for seed in seeds:
        rng = np.random.default_rng(seed)
        x_signal = rng.standard_normal(n_samples)
        x_noise1 = rng.standard_normal(n_samples)
        x_noise2 = rng.standard_normal(n_samples)
        x_control_noise = rng.standard_normal(n_samples)

        y = 3.0 * x_signal + rng.standard_normal(n_samples)

        x_mat = np.column_stack([x_signal, x_noise1, x_noise2, x_control_noise])
        feature_names = ["signal", "noise1", "noise2", "__noise__"]

        # Stage 1: Ridge + Permutation Importance
        reg1 = _make_estimator("ridge", {}, seed)
        reg1.fit(x_mat, y)
        perm1 = permutation_importance(
            reg1, x_mat, y, scoring="neg_mean_absolute_error", n_repeats=30, random_state=seed
        )
        imp1 = dict(zip(feature_names, perm1.importances_mean, strict=True))
        noise_imp1 = imp1["__noise__"]

        if imp1["signal"] > noise_imp1:
            stage1_informative_wins += 1
        if imp1["noise1"] > noise_imp1:
            stage1_noise_wins += 1
        if imp1["noise2"] > noise_imp1:
            stage1_noise_wins += 1

        # Stage 2: XGBoost Regressor
        reg2 = _make_estimator("xgboost_regressor", {}, seed)
        reg2.fit(x_mat, y)
        imp2 = dict(zip(feature_names, reg2.feature_importances_, strict=True))
        noise_imp2 = imp2["__noise__"]

        if imp2["signal"] > noise_imp2:
            stage2_informative_wins += 1
        if imp2["noise1"] > noise_imp2:
            stage2_noise_wins += 1
        if imp2["noise2"] > noise_imp2:
            stage2_noise_wins += 1

    assert stage1_informative_wins >= 4, f"Stage 1 informative wins: {stage1_informative_wins}/5"
    assert stage2_informative_wins >= 4, f"Stage 2 informative wins: {stage2_informative_wins}/5"
    assert stage1_noise_wins <= 6, f"Stage 1 false positive noise wins: {stage1_noise_wins}/10"
    assert stage2_noise_wins <= 6, f"Stage 2 false positive noise wins: {stage2_noise_wins}/10"
