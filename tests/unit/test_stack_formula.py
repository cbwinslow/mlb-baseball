"""Unit coverage for mlb_baseball.model.stack's pure logic -- feature
construction and the missing-value treatment for the optional market
columns. No I/O: DB-facing pieces (train/predict) are covered in
tests/integration/test_model_stack.py.
"""

from decimal import Decimal

from mlb_baseball.model.stack import (
    FEATURE_NAMES,
    _optional_feature,
    _sigmoid,
    feature_row,
)


def test_optional_feature_imputes_neutral_value_and_zero_indicator_when_missing():
    value, present = _optional_feature(None)
    assert value == 0.5
    assert present == 0.0


def test_optional_feature_passes_through_real_value_with_indicator_set():
    value, present = _optional_feature(Decimal("0.62"))
    assert value == 0.62
    assert present == 1.0


def test_optional_feature_accepts_plain_float_too():
    # gold.prediction.home_win_prob comes back as Decimal via psycopg, but
    # feature_row() is also exercised directly with plain floats in tests
    # -- both must work identically, not just the DB-sourced Decimal path.
    value, present = _optional_feature(0.5)
    assert value == 0.5
    assert present == 1.0


def test_feature_row_matches_feature_names_length_and_order():
    row = feature_row(0.4, 0.5, 0.6, 0.62, None)
    assert len(row) == len(FEATURE_NAMES) == 7
    log5, elo, gbm, poly_val, poly_present, kalshi_val, kalshi_present = row
    assert (log5, elo, gbm) == (0.4, 0.5, 0.6)
    assert (poly_val, poly_present) == (0.62, 1.0)
    # kalshi missing -- neutral placeholder, indicator off.
    assert (kalshi_val, kalshi_present) == (0.5, 0.0)


def test_feature_row_handles_both_market_columns_present():
    row = feature_row(0.4, 0.5, 0.6, 0.55, 0.58)
    assert row == [0.4, 0.5, 0.6, 0.55, 1.0, 0.58, 1.0]


def test_feature_row_handles_both_market_columns_missing():
    # The overwhelmingly common real case today -- see stack.py's own
    # docstring on market coverage being a recent, narrow window.
    row = feature_row(0.4, 0.5, 0.6, None, None)
    assert row == [0.4, 0.5, 0.6, 0.5, 0.0, 0.5, 0.0]


def test_sigmoid_of_zero_is_one_half():
    assert abs(_sigmoid(0.0) - 0.5) < 1e-9


def test_sigmoid_is_monotonically_increasing():
    assert _sigmoid(-2.0) < _sigmoid(-0.5) < _sigmoid(0.0) < _sigmoid(0.5) < _sigmoid(2.0)


def test_sigmoid_stays_within_unit_interval_for_extreme_inputs():
    assert 0.0 < _sigmoid(-50.0) < 1e-6
    # +30, not +50: 1/(1+exp(-50)) rounds to exactly 1.0 in float64 (exp(-50)
    # is below float64's ~2.2e-16 precision near 1.0), which would make the
    # strict "< 1.0" bound below impossible to satisfy for any correct
    # implementation -- +30 keeps exp(-30) large enough to stay distinct
    # from 1.0 while still exercising the same "very confident" regime.
    assert 1.0 - 1e-6 < _sigmoid(30.0) < 1.0


def test_bayesian_convex_stacker_simplex_constraint():
    """Verify BayesianConvexStacker satisfies non-negativity and sum-to-1 simplex constraints."""
    import numpy as np

    from mlb_baseball.model.stack import BayesianConvexStacker

    stacker = BayesianConvexStacker(model_names=["log5", "elo", "gbm"], shrinkage_lambda=0.05)
    # Target y is 1 for game 1 and 0 for game 2
    # Model 3 (gbm) is perfectly accurate
    x = np.array(
        [
            [0.5, 0.5, 0.9],
            [0.5, 0.5, 0.1],
            [0.6, 0.4, 0.8],
            [0.4, 0.6, 0.2],
        ]
    )
    y = np.array([1.0, 0.0, 1.0, 0.0])

    stacker.fit(x, y)

    # Weights must be non-negative and sum to 1.0
    assert all(w >= 0.0 for w in stacker.weights)
    assert abs(float(np.sum(stacker.weights)) - 1.0) < 1e-5
    # GBM should have the largest weight
    weights_dict = stacker.get_weights_dict()
    assert weights_dict["gbm"] > weights_dict["log5"]


def test_stack_health_check():
    """Verify stack health check passes cleanly."""
    from mlb_baseball.model.stack import health_check

    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
