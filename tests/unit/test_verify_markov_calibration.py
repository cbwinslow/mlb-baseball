"""Unit coverage for scripts/verify_markov_calibration.py's pure season-
classification logic -- not a package, so loaded directly by path rather
than imported normally (matches no existing precedent among scripts/*.py,
since this is the first one with real branching logic worth unit-testing
in isolation from the database)."""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).parents[2] / "scripts" / "verify_markov_calibration.py"
_spec = importlib.util.spec_from_file_location("verify_markov_calibration", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
verify_markov_calibration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify_markov_calibration)

_classify_seasons = verify_markov_calibration._classify_seasons


def test_classify_seasons_in_sample_when_estimate_matches_eval_exactly():
    assert _classify_seasons(2019, [2019]).startswith("in-sample")


def test_classify_seasons_held_out_when_estimate_all_precede_eval():
    assert _classify_seasons(2019, [2015, 2016, 2017, 2018]).startswith("held-out")


def test_classify_seasons_mixed_when_eval_season_included_with_others():
    # PR review finding: this combination was previously mislabeled
    # "in-sample" by a naive `eval_season not in estimate_seasons` check
    # (it evaluates False here, since 2019 IS in the list) -- but it's
    # not a clean in-sample check either, since it also draws from prior
    # seasons. Must get its own distinct label, not silently fall into
    # either bucket.
    assert _classify_seasons(2019, [2018, 2019]).startswith("mixed")


def test_classify_seasons_rejects_a_future_season():
    # PR review finding: a naive `eval_season not in estimate_seasons`
    # check mislabeled this "held-out" (2019 not in [2020]), when it's
    # actually the opposite -- using future data to "predict" the past,
    # not a valid held-out check at all.
    with pytest.raises(ValueError, match="future"):
        _classify_seasons(2019, [2020])


def test_classify_seasons_rejects_a_future_season_even_when_mixed_with_past():
    # Same leakage, harder to spot: a future season hiding alongside a
    # legitimately-prior one must still be rejected, not diluted into a
    # "held-out" or "mixed" label just because *some* of the seasons are
    # valid.
    with pytest.raises(ValueError, match="future"):
        _classify_seasons(2019, [2015, 2020])
