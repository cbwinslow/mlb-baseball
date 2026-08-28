"""Tests for Bullpen Bridge Sequencing & High-Leverage Handoff Engine (BULLPEN-BRIDGE-01)."""

from mlb_baseball.model.bullpen_bridge import (
    BridgeEvaluationResult,
    BullpenBridgeEngine,
    BullpenBridgeMetrics,
    health_check,
)


def test_elite_bridge_classified_properly():
    """Verify high hold% and leverage match yields DOMINANT bridge chain."""
    engine = BullpenBridgeEngine()

    dodgers = BullpenBridgeMetrics(
        team_id="t1",
        team_name="Dodgers Archetype",
        hold_pct=84.0,
        leverage_match_rate=72.0,
        inherited_score_pct=15.0,
        high_leverage_innings=100.0,
        clean_inning_pct=75.0,
    )

    res: BridgeEvaluationResult = engine.evaluate_bridge(dodgers)

    assert res.bsei_score > 118.0
    assert res.hlhrs_runs_saved > 6.0
    assert res.bridge_tier == "DOMINANT_LOCKDOWN_BRIDGE_CHAIN"
    assert res.is_elite_bridge is True


def test_leaking_bridge_triggers_liability():
    """Verify low hold% and high inherited score% yields LIABILITY tier."""
    engine = BullpenBridgeEngine()

    bad_pen = BullpenBridgeMetrics(
        team_id="t2",
        team_name="Bad Bullpen",
        hold_pct=45.0,
        leverage_match_rate=32.0,
        inherited_score_pct=48.0,
        high_leverage_innings=75.0,
    )

    res: BridgeEvaluationResult = engine.evaluate_bridge(bad_pen)

    assert res.bsei_score < 100.0
    assert res.hlhrs_runs_saved < 0.0
    assert res.bridge_tier == "LEAKING_BRIDGE_HANDOFF_LIABILITY"
    assert res.is_elite_bridge is False


def test_bullpen_bridge_health_check():
    """Verify bullpen bridge health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
