"""Unit tests for Catcher Pop Time Engine (POPTIME-01, ADR-173)."""

from mlb_baseball.model.poptime import (
    CatcherPopTimeEngine,
    CatcherPopTimeMetrics,
    health_check,
)


def test_elite_pop_time_catcher_has_high_cs_rate_and_csaa_runs():
    """Verify 1.84s pop time yields high expected CS% and ELITE_POP_TIME."""
    engine = CatcherPopTimeEngine()

    realmuto = CatcherPopTimeMetrics(
        catcher_id="c1",
        catcher_name="J.T. Realmuto",
        pop_time_s=1.84,
        arm_velocity_mph=89.0,
        attempts_faced=70,
    )

    res = engine.evaluate_pop_time(realmuto, benchmark_slide_time=1.98)

    assert res.expected_cs_pct > 80.0
    assert res.csaa_runs_saved > 4.0
    assert res.catcher_tier == "ELITE_POP_TIME"


def test_slow_pop_time_catcher_classified_as_liability():
    """Verify 2.12s pop time yields low expected CS% and SLOW_RELEASE_LIABILITY."""
    engine = CatcherPopTimeEngine()

    slow = CatcherPopTimeMetrics(
        catcher_id="c2",
        catcher_name="Slow Release Catcher",
        pop_time_s=2.12,
        arm_velocity_mph=78.0,
        attempts_faced=60,
    )

    res = engine.evaluate_pop_time(slow, benchmark_slide_time=1.98)

    assert res.expected_cs_pct < 40.0
    assert res.csaa_runs_saved < 0.0
    assert res.catcher_tier == "SLOW_RELEASE_LIABILITY"


def test_poptime_health_check():
    """Verify pop time health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Pop time verified" in checks[0].detail
