"""Unit tests for Batter Pull-Side Groundball Defense Engine (PULL-GB-01, ADR-203)."""

from mlb_baseball.model.pull_gb import (
    BatterPullGBMetrics,
    InfieldPositioningGBEngine,
    health_check,
)


def test_heavy_pull_groundballer_requires_extreme_shading():
    """Verify high pull GB% triggers EXTREME_PULL_SHADING_REQUIRED and deep positioning."""
    engine = InfieldPositioningGBEngine()

    schwarber = BatterPullGBMetrics(
        batter_id="b1",
        batter_name="Kyle Schwarber Archetype",
        batter_side="L",
        groundball_rate_pct=52.0,
        pull_groundball_pct=74.0,
        oppo_groundball_pct=8.0,
        hard_pull_gb_pct=50.0,
        groundball_count=150,
    )

    res = engine.evaluate_positioning(schwarber)

    assert res.optimal_depth_ft > 155.0
    assert res.gbti_score > 125.0
    assert res.pdrs_runs_saved > 10.0
    assert res.positioning_tier == "EXTREME_PULL_SHADING_REQUIRED"
    assert res.requires_extreme_shading is True


def test_neutral_groundball_hitter_yields_neutral_positioning():
    """Verify balanced spray yields STRAIGHT_UP_NEUTRAL_POSITIONING."""
    engine = InfieldPositioningGBEngine()

    neutral = BatterPullGBMetrics(
        batter_id="b2",
        batter_name="Balanced Spray Hitter",
        batter_side="R",
        groundball_rate_pct=42.0,
        pull_groundball_pct=46.0,
        oppo_groundball_pct=26.0,
        hard_pull_gb_pct=30.0,
        groundball_count=110,
    )

    res = engine.evaluate_positioning(neutral)

    assert res.positioning_tier == "STRAIGHT_UP_NEUTRAL_POSITIONING"
    assert res.requires_extreme_shading is False


def test_pull_gb_health_check():
    """Verify pull GB health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Pull GB verified" in checks[0].detail
