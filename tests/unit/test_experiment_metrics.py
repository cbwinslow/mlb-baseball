import math

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
