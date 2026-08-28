"""Unit tests for Probability Calibration & Symmetric Mirror Engine (CALIB-01, ADR-118)."""

import numpy as np
import pytest

from mlb_baseball.model.calibration import (
    HomeAdvantageCalibrator,
    PlattCalibrator,
    create_symmetric_mirror_dataset,
    evaluate_calibration,
    health_check,
)


def test_home_advantage_calibrator():
    """Verify HFA recalibration adjusts for model bias and preserves road favorites."""
    cal = HomeAdvantageCalibrator(baseline_hfa_rate=0.535)

    # 1. Evenly matched game with 0.5576 implicit model bias -> recalibrates to exactly 0.535
    adj_even = cal.adjust_home_win_prob(0.5576, model_implicit_home_rate=0.5576)
    assert pytest.approx(adj_even, abs=1e-4) == 0.5350

    # 2. Road favorite (e.g. raw 0.400) -> correctly stays a road favorite (< 0.50)
    adj_road = cal.adjust_home_win_prob(0.4000, model_implicit_home_rate=0.5576)
    assert adj_road < 0.4000
    assert adj_road < 0.5000

    # 3. Strong home favorite (raw 0.700) -> recalibrates downwards to eliminate inflation
    adj_home = cal.adjust_home_win_prob(0.7000, model_implicit_home_rate=0.5576)
    assert 0.600 < adj_home < 0.700


def test_platt_calibrator_fitting():
    """Verify Platt scaling fitting on synthetic overconfident probabilities."""
    cal = PlattCalibrator()

    # Synthetic overconfident probabilities: model predicts 0.85/0.15 vs true rate 0.65/0.35
    rng = np.random.default_rng(42)
    n = 200
    raw_p = np.concatenate([np.full(n // 2, 0.85), np.full(n // 2, 0.15)])
    y_true = np.concatenate([rng.binomial(1, 0.65, n // 2), rng.binomial(1, 0.35, n // 2)])

    cal.fit(y_true, raw_p)
    cal_p = cal.predict(raw_p)

    assert len(cal_p) == n
    # Calibrated probabilities should shrink towards center
    assert np.mean(cal_p[: n // 2]) < 0.85
    assert np.mean(cal_p[n // 2 :]) > 0.15


def test_evaluate_calibration_metrics():
    """Verify ECE, Brier score, and reliability bins computation."""
    y_true = [1, 1, 1, 0, 0, 0, 1, 0, 1, 0]
    y_prob = [0.9, 0.8, 0.7, 0.3, 0.2, 0.1, 0.6, 0.4, 0.8, 0.2]

    report = evaluate_calibration(y_true, y_prob, n_bins=5)

    assert report.sample_size == 10
    assert 0.0 <= report.expected_calibration_error <= 1.0
    assert 0.0 <= report.brier_score <= 1.0
    assert len(report.bins) == 5


def test_create_symmetric_mirror_dataset():
    """Verify mirror data augmentation doubles sample size with exact negative symmetry."""
    x_home = np.array([[3.0, 1.0], [4.0, 2.0]])
    x_away = np.array([[1.0, 2.0], [2.0, 1.0]])
    y = np.array([1.0, 0.0])

    x_aug, y_aug = create_symmetric_mirror_dataset(x_home, x_away, y)

    # Doubled rows
    assert x_aug.shape == (4, 2)
    assert y_aug.shape == (4,)

    # First half: x_home - x_away
    np.testing.assert_array_equal(x_aug[:2], np.array([[2.0, -1.0], [2.0, 1.0]]))
    # Second half: x_away - x_home (exact negation)
    np.testing.assert_array_equal(x_aug[2:], -x_aug[:2])
    # Labels inverted
    np.testing.assert_array_equal(y_aug[2:], 1.0 - y)


def test_calibration_health_check():
    """Verify calibration engine operational health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "HFA" in checks[0].detail
