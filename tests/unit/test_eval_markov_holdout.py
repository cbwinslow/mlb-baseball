"""Pure scoring/verdict helpers in scripts/eval_markov_holdout.py.

Not a package -- loaded by path, matching
tests/unit/test_verify_markov_calibration.py.
"""

import importlib.util
import math
from pathlib import Path

import pytest

from mlb_baseball.model.evaluation import Prediction
from mlb_baseball.model.gbm import MIN_PRACTICAL_LOG_LOSS_IMPROVEMENT

_SCRIPT = Path(__file__).parents[2] / "scripts" / "eval_markov_holdout.py"
_spec = importlib.util.spec_from_file_location("eval_markov_holdout", _SCRIPT)
assert _spec is not None and _spec.loader is not None
eh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eh)


def _pred(prob: float, actual: bool) -> Prediction:
    return Prediction("g", "markov-v1", prob, actual)


def test_per_game_losses_matches_hand_calc_and_clips_extremes():
    losses = eh._per_game_losses([_pred(0.75, True), _pred(0.25, True), _pred(0.0, True)])
    assert losses[0] == pytest.approx(-math.log(0.75))
    assert losses[1] == pytest.approx(-math.log(0.25))
    # 0.0 is clipped to 1e-15, not -inf.
    assert losses[2] == pytest.approx(-math.log(1e-15))


def test_paired_diff_ci_is_positive_when_markov_is_clearly_better():
    # markov nails every game; baseline is a coin flip.
    markov = [_pred(0.95, True), _pred(0.05, False), _pred(0.9, True), _pred(0.1, False)]
    baseline = [_pred(0.5, True), _pred(0.5, False), _pred(0.5, True), _pred(0.5, False)]
    point, low, high = eh._paired_diff_ci(markov, baseline, seed=0)
    assert point > 0
    assert low > 0  # CI excludes zero
    assert low <= point <= high


def test_paired_diff_ci_is_seed_deterministic():
    markov = [_pred(0.7, True), _pred(0.4, False), _pred(0.6, True)]
    baseline = [_pred(0.55, True), _pred(0.45, False), _pred(0.5, True)]
    assert eh._paired_diff_ci(markov, baseline, seed=3) == eh._paired_diff_ci(
        markov, baseline, seed=3
    )


def test_verdict_requires_both_the_margin_and_a_ci_off_zero():
    m = MIN_PRACTICAL_LOG_LOSS_IMPROVEMENT
    assert eh._verdict(point=m + 0.01, low=0.001, high=0.02) == "markov-v1 better"
    # point clears the margin but the CI still spans zero -> noise
    assert eh._verdict(point=m + 0.01, low=-0.001, high=0.03) == "within noise"
    # CI is off zero but the effect is below the practical margin -> noise
    assert eh._verdict(point=0.0005, low=0.0001, high=0.001) == "within noise"
    assert eh._verdict(point=-(m + 0.01), low=-0.03, high=-0.002) == "baseline better"
