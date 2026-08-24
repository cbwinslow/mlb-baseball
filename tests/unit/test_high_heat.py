"""Unit tests for Batter High-Fastball Top-of-Zone Whiff Engine (HIGH-HEAT-01, ADR-231)."""

from mlb_baseball.model.high_heat import (
    BatterHighHeatEngine,
    BatterHighHeatMetrics,
    HighHeatEvaluationResult,
    health_check,
)


def test_high_heat_crusher_classified_properly():
    """Verify sub-15% whiff rate on elevated fastballs yields ELITE_HIGH_FASTBALL_CRUSHER."""
    engine = BatterHighHeatEngine()

    freeman = BatterHighHeatMetrics(
        batter_id="b1",
        batter_name="Freddie Freeman Archetype",
        high_fb_swing_rate_pct=68.0,
        high_fb_whiff_rate_pct=12.0,
        high_fb_hard_hit_pct=54.0,
        high_fb_opportunities=260,
    )

    res: HighHeatEvaluationResult = engine.evaluate_high_heat(freeman)

    assert res.hhevi_score > 125.0
    assert res.hfpr_runs_produced > 15.0
    assert res.heat_tier == "ELITE_HIGH_FASTBALL_CRUSHER"
    assert res.is_elite_crusher is True


def test_vulnerable_high_whiff_triggers_vulnerable_tier():
    """Verify 36%+ whiff rate on elevated fastballs triggers TOP_ZONE_ELEVATION_VULNERABLE."""
    engine = BatterHighHeatEngine()

    vulnerable = BatterHighHeatMetrics(
        batter_id="b2",
        batter_name="Elevated Heat Vulnerable",
        high_fb_swing_rate_pct=64.0,
        high_fb_whiff_rate_pct=38.0,
        high_fb_hard_hit_pct=22.0,
        high_fb_opportunities=200,
    )

    res = engine.evaluate_high_heat(vulnerable)

    assert res.heat_tier == "TOP_ZONE_ELEVATION_VULNERABLE"
    assert res.is_elite_crusher is False


def test_high_heat_health_check():
    """Verify high heat health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "High Heat verified" in checks[0].detail
