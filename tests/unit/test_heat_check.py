"""Unit tests for Batter In-Zone Fastball Contact Engine (HEAT-CHECK-01, ADR-243)."""

from mlb_baseball.model.heat_check import (
    BatterHeatCheckEngine,
    BatterHeatCheckMetrics,
    HeatCheckEvaluationResult,
    health_check,
)


def test_heat_punisher_classified_properly():
    """Verify low whiff and high hard-hit yields HEAT_SEEKING_FASTBALL_PUNISHER."""
    engine = BatterHeatCheckEngine()

    alvarez = BatterHeatCheckMetrics(
        batter_id="b1",
        batter_name="Yordan Alvarez Archetype",
        in_zone_fb_contact_pct=90.0,
        in_zone_fb_hard_hit_pct=60.0,
        in_zone_fb_whiff_pct=10.0,
        in_zone_fb_swings_count=220,
    )

    res: HeatCheckEvaluationResult = engine.evaluate_heat_check(alvarez)

    assert res.izhsmi_score > 125.0
    assert res.izfpr_runs_produced > 15.0
    assert res.smash_tier == "HEAT_SEEKING_FASTBALL_PUNISHER"
    assert res.is_heat_punisher is True


def test_vulnerable_whiff_machine_triggers_vulnerable_tier():
    """Verify high in-zone whiff triggers HIGH_VELO_VULNERABLE_WHIFF_MACHINE."""
    engine = BatterHeatCheckEngine()

    whiffer = BatterHeatCheckMetrics(
        batter_id="b2",
        batter_name="High Velo Vulnerable",
        in_zone_fb_contact_pct=68.0,
        in_zone_fb_hard_hit_pct=26.0,
        in_zone_fb_whiff_pct=32.0,
        in_zone_fb_swings_count=140,
    )

    res = engine.evaluate_heat_check(whiffer)

    assert res.smash_tier == "HIGH_VELO_VULNERABLE_WHIFF_MACHINE"
    assert res.is_heat_punisher is False


def test_heat_check_health_check():
    """Verify heat check health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Heat Check verified" in checks[0].detail
