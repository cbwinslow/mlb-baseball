"""Unit tests for Catcher Pop Time Engine (POPTIME-01, ADR-173)."""

from mlb_baseball.model.poptime import (
    CatcherPopTimeEngine,
    CatcherPopTimeMetrics,
    health_check,
)


def test_elite_pop_time_catcher_has_high_cs_rate_and_csaa_runs():
    """Verify 1.84s pop time yields high expected CS% and ELITE_POP_TIME.

    Threshold recalibrated for POPTIME-01 (sigmoid intercept fix): the
    formula now anchors delta_t=0 at the real ~21% league-average CS%
    instead of 50%, so a 1.84s pop time (only 0.14s under benchmark)
    correctly lands around 59%, not the pre-fix bug's inflated 80%+.
    """
    engine = CatcherPopTimeEngine()

    realmuto = CatcherPopTimeMetrics(
        catcher_id="c1",
        catcher_name="J.T. Realmuto",
        pop_time_s=1.84,
        arm_velocity_mph=89.0,
        attempts_faced=70,
    )

    res = engine.evaluate_pop_time(realmuto, benchmark_slide_time=1.98)

    assert res.expected_cs_pct > 55.0
    assert res.csaa_runs_saved > 4.0
    assert res.catcher_tier == "ELITE_POP_TIME"


def test_default_pop_time_catcher_is_not_mislabeled_elite():
    """Regression test for POPTIME-01.

    Feeding the class's own default/neutral input (pop_time_s=1.95, i.e.
    delta_t=0.03 against the default 1.98s benchmark -- essentially a
    league-average catcher) must no longer compute an inflated ~59% CS%
    and get tagged ELITE_POP_TIME the way the pre-fix sigmoid did. It
    should land close to the real league-average CS% (~21%) and read as
    an unremarkable tier, not ELITE_POP_TIME.
    """
    engine = CatcherPopTimeEngine()

    league_avg = CatcherPopTimeMetrics(catcher_id="c3", catcher_name="League Average Catcher")

    res = engine.evaluate_pop_time(league_avg)

    assert 15.0 < res.expected_cs_pct < 35.0
    assert res.catcher_tier != "ELITE_POP_TIME"


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
