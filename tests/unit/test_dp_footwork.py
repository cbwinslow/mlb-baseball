"""Unit tests for Middle Infield Double-Play Turn Speed Engine (DP-FOOTWORK-01, ADR-241)."""

from mlb_baseball.model.dp_footwork import (
    DpFootworkEvaluationResult,
    InfieldDpFootworkEngine,
    InfieldDpFootworkMetrics,
    health_check,
)


def test_lightning_master_classified_properly():
    """Verify sub-0.60s pivot and 88%+ conversion yields LIGHTNING_ACROBATIC_PIVOT_MASTER."""
    engine = InfieldDpFootworkEngine()

    semien = InfieldDpFootworkMetrics(
        fielder_id="f1",
        fielder_name="Marcus Semien Archetype",
        position="2B",
        pivot_time_sec=0.56,
        throw_velo_mph=87.0,
        dp_conversion_pct=90.0,
        dp_turn_opportunities=75,
    )

    res: DpFootworkEvaluationResult = engine.evaluate_dp_footwork(semien)

    assert res.dpfti_score > 125.0
    assert res.dptaa_turns_saved > 10.0
    assert res.dprv_runs_saved > 4.5
    assert res.footwork_tier == "LIGHTNING_ACROBATIC_PIVOT_MASTER"
    assert res.is_lightning_master is True


def test_clunky_infielder_triggers_liability_tier():
    """Verify slow pivot and sub-60% conversion triggers CLUNKY_FOOTWORK_DP_LIABILITY."""
    engine = InfieldDpFootworkEngine()

    clunky = InfieldDpFootworkMetrics(
        fielder_id="f2",
        fielder_name="Slow Pivot SS",
        position="SS",
        pivot_time_sec=0.90,
        throw_velo_mph=70.0,
        dp_conversion_pct=54.0,
        dp_turn_opportunities=50,
    )

    res = engine.evaluate_dp_footwork(clunky)

    assert res.footwork_tier == "CLUNKY_FOOTWORK_DP_LIABILITY"
    assert res.is_lightning_master is False


def test_dp_footwork_health_check():
    """Verify dp footwork health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "DP Footwork verified" in checks[0].detail
