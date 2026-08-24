"""Unit tests for Outfield Wall Collision & Robbery Engine (WALL-01, ADR-177)."""

from mlb_baseball.model.wall import (
    OutfielderWallMetrics,
    OutfieldWallEngine,
    health_check,
)


def test_home_run_robber_classified_as_elite_wall_thief():
    """Verify multiple HR robberies and wall catches yield ELITE_WALL_THIEF and high run savings."""
    engine = OutfieldWallEngine()

    thief = OutfielderWallMetrics(
        fielder_id="f1",
        fielder_name="Kevin Pillar Archetype",
        position="CF",
        hr_robberies=3,
        extra_base_wall_catches=7,
        wall_crashes_unsuccessful=0,
        opportunities=30,
    )

    res = engine.evaluate_wall_defense(thief)

    assert res.total_wall_runs_saved > 8.0
    assert res.wall_defense_tier == "ELITE_WALL_THIEF"
    assert res.hr_robberies == 3


def test_timid_wall_fielder_triggers_liability_tier():
    """Verify repeated failed wall attempts result in WALL_TIMID_FIELDER."""
    engine = OutfieldWallEngine()

    timid = OutfielderWallMetrics(
        fielder_id="f2",
        fielder_name="Timid Fielder",
        position="LF",
        hr_robberies=0,
        extra_base_wall_catches=1,
        wall_crashes_unsuccessful=4,
        opportunities=25,
    )

    res = engine.evaluate_wall_defense(timid)

    assert res.total_wall_runs_saved < -1.5
    assert res.wall_defense_tier == "WALL_TIMID_FIELDER"


def test_wall_health_check():
    """Verify outfield wall health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Wall defense verified" in checks[0].detail
