"""Unit tests for Batter vs. Pitcher (BvP) Arsenal Interaction Engine (BVP-01, ADR-135)."""

from mlb_baseball.model.bvp import (
    BatterArsenalPreferences,
    EmpiricalBayesBvPEngine,
    PitcherArsenalMix,
    health_check,
)


def test_empirical_bayes_bvp_shrinkage_on_small_sample():
    """Verify small sample (15 PA) .550 wOBA is strongly shrunk toward platoon prior."""
    engine = EmpiricalBayesBvPEngine()

    res = engine.evaluate_matchup(
        batter_id="b1",
        batter_name="Batter",
        pitcher_id="p1",
        pitcher_name="Pitcher",
        batter_woba_vs_hand=0.340,
        pitcher_woba_vs_hand=0.300,
        observed_pa=15,
        observed_woba=0.550,
    )

    assert res.observed_pa == 15
    assert res.raw_bvp_woba == 0.550
    # Prior should be ~0.325
    assert 0.315 <= res.platoon_prior_woba <= 0.335
    # Shrunk wOBA with 15 PA out of 365 total weight should be heavily weighted to prior
    assert res.shrunk_bvp_woba < 0.350


def test_arsenal_interaction_slider_crusher():
    """Verify batter with +2.5 RV/100 on sliders gets positive boost vs slider-heavy pitcher."""
    engine = EmpiricalBayesBvPEngine()

    slider_crusher = BatterArsenalPreferences(rv_slider=+2.5, rv_four_seam=-0.5)
    slider_heavy_pitcher = PitcherArsenalMix(pct_slider=0.50, pct_four_seam=0.50)

    res = engine.evaluate_matchup(
        batter_id="b1",
        batter_name="Slider Crusher",
        pitcher_id="p1",
        pitcher_name="Slider Heavy",
        batter_woba_vs_hand=0.330,
        pitcher_woba_vs_hand=0.310,
        observed_pa=0,
        batter_prefs=slider_crusher,
        pitcher_mix=slider_heavy_pitcher,
    )

    # 0.50 * (+2.5) + 0.50 * (-0.5) = +1.0 RV/100
    assert res.arsenal_interaction_rv100 == 1.00
    assert res.composite_matchup_woba > res.platoon_prior_woba


def test_bvp_health_check():
    """Verify bvp health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Empirical Bayes shrinkage verified" in checks[0].detail
