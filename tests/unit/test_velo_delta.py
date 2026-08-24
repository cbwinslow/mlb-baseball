"""Unit tests for Pitcher Arsenals Separation & Velo Delta Engine (VELO-DELTA-01, ADR-200)."""

from mlb_baseball.model.velo_delta import (
    PitcherArsenalSeparationMetrics,
    PitcherVeloDeltaEngine,
    health_check,
)


def test_wide_separation_pitcher_classified_as_elite_disruptor():
    """Verify large velo gap and IVB depth separation yields ELITE_VELO_BAND_DISRUPTOR."""
    engine = PitcherVeloDeltaEngine()

    webb = PitcherArsenalSeparationMetrics(
        pitcher_id="p1",
        pitcher_name="Logan Webb Archetype",
        fastball_velo_mph=94.0,
        changeup_velo_mph=83.0,
        slider_velo_mph=84.5,
        curveball_velo_mph=79.0,
        fastball_ivb_in=15.0,
        changeup_ivb_in=2.0,
    )

    res = engine.evaluate_separation(webb)

    assert res.fb_ch_velo_delta_mph >= 11.0
    assert res.fb_ch_ivb_delta_in >= 13.0
    assert res.vddi_score > 115.0
    assert res.whiff_boost_multiplier > 1.05
    assert res.separation_tier == "ELITE_VELO_BAND_DISRUPTOR"
    assert res.is_elite_disruptor is True


def test_flat_homogeneous_pitcher_triggers_liability_tier():
    """Verify minimal velo gap and shallow drop triggers DANGEROUS_FLAT_HOMOGENEOUS_ARSENAL."""
    engine = PitcherVeloDeltaEngine()

    flat = PitcherArsenalSeparationMetrics(
        pitcher_id="p2",
        pitcher_name="Homogeneous Pitcher",
        fastball_velo_mph=91.0,
        changeup_velo_mph=87.5,
        slider_velo_mph=86.0,
        curveball_velo_mph=84.0,
        fastball_ivb_in=12.0,
        changeup_ivb_in=9.0,
    )

    res = engine.evaluate_separation(flat)

    assert res.fb_ch_velo_delta_mph < 4.0
    assert res.vddi_score < 85.0
    assert res.separation_tier == "DANGEROUS_FLAT_HOMOGENEOUS_ARSENAL"
    assert res.is_elite_disruptor is False


def test_velo_delta_health_check():
    """Verify velo delta health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Velo delta verified" in checks[0].detail
