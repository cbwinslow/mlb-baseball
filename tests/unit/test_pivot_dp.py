"""Unit tests for Infield Double Play Pivot Kinematics Engine (PIVOT-DP-01, ADR-197)."""

from mlb_baseball.model.pivot_dp import (
    InfieldPivotDPEngine,
    InfieldPivotMetrics,
    health_check,
)


def test_quick_second_baseman_classified_as_lightning_turner():
    """Verify fast pivot turn time and high conversion yields LIGHTNING_PIVOT_TURNER."""
    engine = InfieldPivotDPEngine()

    altuve = InfieldPivotMetrics(
        fielder_id="f1",
        fielder_name="Elite Middle Infielder",
        position="2B",
        pivot_turn_time_s=0.67,
        relay_throw_velo_mph=87.5,
        double_plays_turned=70,
        double_play_opportunities=82,
        failed_pivot_turns=8,
        wild_relay_throws=0,
    )

    res = engine.evaluate_pivot(altuve)

    assert res.dp_conversion_pct > 80.0
    assert res.dpti_score > 120.0
    assert res.dpts_runs_saved > 5.0
    assert res.pivot_tier == "LIGHTNING_PIVOT_TURNER"
    assert res.is_lightning_turner is True


def test_slow_pivot_shortstop_triggers_liability_tier():
    """Verify sluggish turn time and multiple wild throws triggers SLOW_PIVOT_LIABILITY."""
    engine = InfieldPivotDPEngine()

    slow_ss = InfieldPivotMetrics(
        fielder_id="f2",
        fielder_name="Slow SS",
        position="SS",
        pivot_turn_time_s=0.89,
        relay_throw_velo_mph=78.0,
        double_plays_turned=42,
        double_play_opportunities=78,
        failed_pivot_turns=30,
        wild_relay_throws=4,
    )

    res = engine.evaluate_pivot(slow_ss)

    assert res.dp_conversion_pct < 60.0
    assert res.dpts_runs_saved < 0.0
    assert res.pivot_tier == "SLOW_PIVOT_LIABILITY"
    assert res.is_lightning_turner is False


def test_pivot_dp_health_check():
    """Verify pivot DP health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Pivot DP verified" in checks[0].detail
