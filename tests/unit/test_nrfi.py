"""Unit tests for First-Inning Run Scored (NRFI / YRFI) Valuation Engine (NRFI-01, ADR-156)."""

import pytest

from mlb_baseball.model.nrfi import (
    FirstInningValuationEngine,
    InningOneMatchupInputs,
    health_check,
)


def test_ace_pitchers_matchup_yields_high_nrfi_probability():
    """Verify duel between low-ERA starters results in high P(NRFI)."""
    engine = FirstInningValuationEngine()

    pitcher_duel = InningOneMatchupInputs(
        home_team="SEA",
        away_team="HOU",
        home_starter_inn1_era=2.40,
        away_starter_inn1_era=2.60,
        home_top3_woba=0.315,
        away_top3_woba=0.320,
        park_factor=0.92,
    )

    res = engine.evaluate_first_inning(pitcher_duel)

    assert res.nrfi_probability > 0.58
    assert res.recommended_side == "NRFI"
    assert res.fair_nrfi_american < -150


def test_coors_field_slugfest_yields_high_yrfi_probability():
    """Verify high-offense, high-ERA matchup produces elevated YRFI probability."""
    engine = FirstInningValuationEngine()

    coors_game = InningOneMatchupInputs(
        home_team="COL",
        away_team="CIN",
        home_starter_inn1_era=5.20,
        away_starter_inn1_era=4.90,
        home_top3_woba=0.370,
        away_top3_woba=0.365,
        park_factor=1.35,
    )

    res = engine.evaluate_first_inning(coors_game)

    assert res.yrfi_probability > 0.60
    assert res.recommended_side == "YRFI"
    assert res.fair_yrfi_american < 0


def test_first_inning_poisson_baseline_is_the_documented_040_constant():
    """Regression (NRFI-01): the half-inning Poisson mean must stay 0.40 -- the
    value ADR-156 and docs/THEORY_AND_METHODOLOGY.md section 42.1 both define the
    formula with. A neutral matchup (all dataclass defaults, park_factor 1.0)
    reduces to mu_top = 0.40 * (3.60/3.90) and mu_bot = 0.40 * (0.340/0.335) *
    (3.80/3.90), so P(NRFI) = exp(-(mu_top + mu_bot)) ~= 0.4655. A silent switch
    to 0.52 (or any other unvalidated baseline) moves this materially and must
    fail here.
    """
    engine = FirstInningValuationEngine()

    res = engine.evaluate_first_inning(InningOneMatchupInputs(home_team="HOME", away_team="AWAY"))

    assert res.nrfi_probability == pytest.approx(0.4655, abs=1e-3)
    assert res.recommended_side == "NEUTRAL"


def test_nrfi_health_check():
    """Verify NRFI health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "NRFI verified" in checks[0].detail
