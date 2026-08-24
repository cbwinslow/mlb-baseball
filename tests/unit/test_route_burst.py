"""Unit tests for Outfielder Route Burst & Jump Engine (ROUTE-BURST-01, ADR-213)."""

from mlb_baseball.model.route_burst import (
    OutfielderBurstRouteMetrics,
    OutfielderRouteBurstEngine,
    health_check,
)


def test_elite_ballhawk_classified_properly():
    """Verify sub-0.36s reaction and 96%+ route efficiency yields ELITE_BALLHAWK_BURST_ENGINE."""
    engine = OutfielderRouteBurstEngine()

    kiermaier = OutfielderBurstRouteMetrics(
        fielder_id="f1",
        fielder_name="Kevin Kiermaier Archetype",
        position="CF",
        reaction_time_sec=0.32,
        burst_velocity_ft_s=29.5,
        route_efficiency_pct=98.0,
        opportunity_count=160,
    )

    res = engine.evaluate_route_burst(kiermaier)

    assert res.brfei_score > 125.0
    assert res.oaa_jump_runs_saved > 8.0
    assert res.range_tier == "ELITE_BALLHAWK_BURST_ENGINE"
    assert res.is_elite_ballhawk is True


def test_poor_route_fast_fielder_triggers_inefficient_tier():
    """Verify fast burst with poor route efficiency yields RAW_SPEED_INEFFICIENT_ROUTER."""
    engine = OutfielderRouteBurstEngine()

    inefficient = OutfielderBurstRouteMetrics(
        fielder_id="f2",
        fielder_name="Fast but Inefficient",
        position="CF",
        reaction_time_sec=0.46,
        burst_velocity_ft_s=28.8,
        route_efficiency_pct=86.5,
        opportunity_count=110,
    )

    res = engine.evaluate_route_burst(inefficient)

    assert res.range_tier == "RAW_SPEED_INEFFICIENT_ROUTER"
    assert res.is_elite_ballhawk is False


def test_route_burst_health_check():
    """Verify route burst health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Route Burst verified" in checks[0].detail
