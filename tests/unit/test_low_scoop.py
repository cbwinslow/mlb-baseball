"""Unit tests for Catcher Low-Pitch Scoop & Framing Lift Engine (LOW-SCOOP-01, ADR-225)."""

from mlb_baseball.model.low_scoop import (
    CatcherLowScoopEngine,
    CatcherLowScoopMetrics,
    LowScoopEvaluationResult,
    health_check,
)


def test_elite_lifter_classified_properly():
    """Verify 64%+ low strike rate and fast scoop yields ELITE_LOW_ZONE_LIFTER."""
    engine = CatcherLowScoopEngine()

    bailey = CatcherLowScoopMetrics(
        catcher_id="c1",
        catcher_name="Patrick Bailey Archetype",
        low_zone_called_strike_pct=66.0,
        upward_scoop_speed_fps=5.0,
        glove_drop_rate_pct=6.0,
        low_zone_opportunities=260,
    )

    res: LowScoopEvaluationResult = engine.evaluate_low_scoop(bailey)

    assert res.bzsfr_score > 125.0
    assert res.extra_strikes_created > 40.0
    assert res.lzfs_runs_saved > 5.0
    assert res.framing_tier == "ELITE_LOW_ZONE_LIFTER"
    assert res.is_elite_lifter is True


def test_stabber_triggers_liability_tier():
    """Verify sub-38% low strike rate triggers STAB_DOWN_GLOVE_DROPPING_LIABILITY."""
    engine = CatcherLowScoopEngine()

    stabber = CatcherLowScoopMetrics(
        catcher_id="c2",
        catcher_name="Glove Stabber",
        low_zone_called_strike_pct=34.0,
        upward_scoop_speed_fps=2.2,
        glove_drop_rate_pct=38.0,
        low_zone_opportunities=200,
    )

    res = engine.evaluate_low_scoop(stabber)

    assert res.framing_tier == "STAB_DOWN_GLOVE_DROPPING_LIABILITY"
    assert res.is_elite_lifter is False


def test_low_scoop_health_check():
    """Verify low scoop health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Low Scoop verified" in checks[0].detail
