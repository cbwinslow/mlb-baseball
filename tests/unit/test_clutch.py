"""Unit tests for Batter Clutch Context Engine (CLUTCH-01, ADR-167)."""

from mlb_baseball.model.clutch import (
    BatterClutchEngine,
    BatterClutchRawStats,
    health_check,
)


def test_high_wpa_clutch_hitter_classified_as_clutch_performer():
    """Verify strong performance in high leverage yields CLUTCH_PERFORMER."""
    engine = BatterClutchEngine()

    clutch_slugger = BatterClutchRawStats(
        batter_id="b1",
        batter_name="October Legend",
        woba_overall=0.345,
        pa_high_li=130,
        woba_high_li=0.435,
        wpa=4.10,
        pli=1.20,
    )

    res = engine.evaluate_clutch(clutch_slugger, shrinkage_m=600.0)

    assert res.clutch_woba_delta > 0.012
    assert res.clutch_tier == "CLUTCH_PERFORMER"
    assert res.is_high_leverage_asset is True


def test_leverage_collapse_hitter_classified_appropriately():
    """Verify severe dip in high leverage triggers LEVERAGE_COLLAPSE."""
    engine = BatterClutchEngine()

    choker = BatterClutchRawStats(
        batter_id="b2",
        batter_name="Low Leverage Producer",
        woba_overall=0.340,
        pa_high_li=110,
        woba_high_li=0.230,
        wpa=-1.50,
        pli=1.10,
    )

    res = engine.evaluate_clutch(choker, shrinkage_m=600.0)

    assert res.clutch_woba_delta < -0.012
    assert res.clutch_tier == "LEVERAGE_COLLAPSE"
    assert res.is_high_leverage_asset is False


def test_clutch_health_check():
    """Verify clutch health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Clutch verified" in checks[0].detail
