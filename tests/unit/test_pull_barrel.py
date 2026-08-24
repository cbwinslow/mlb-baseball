"""Unit tests for Batter Pull-Air Barrel Conversion Engine (PULL-BARREL-01, ADR-211)."""

from mlb_baseball.model.pull_barrel import (
    BatterPullBarrelEngine,
    BatterPullBarrelMetrics,
    health_check,
)


def test_pull_air_crusher_classified_as_optimal_crusher():
    """Verify high pull FB% and high pull barrel rate yields OPTIMAL_PULL_AIR_POWER_CRUSHER."""
    engine = BatterPullBarrelEngine()

    jram = BatterPullBarrelMetrics(
        batter_id="b1",
        batter_name="Jose Ramirez Archetype",
        flyball_pull_pct=40.0,
        pull_barrel_pct=36.0,
        oppo_barrel_pct=8.0,
        pulled_air_count=90,
        total_bbe_count=300,
    )

    res = engine.evaluate_pull_barrel(jram)

    assert res.pabci_score > 125.0
    assert res.surplus_home_runs > 2.5
    assert res.pabsv_runs_saved > 3.5
    assert res.power_tier == "OPTIMAL_PULL_AIR_POWER_CRUSHER"
    assert res.is_optimal_crusher is True


def test_popup_risk_triggers_harmless_tier():
    """Verify high pull flyball rate with low barrel rate triggers HARMLESS_PULL_AIR_POPUP_RISK."""
    engine = BatterPullBarrelEngine()

    popup_batter = BatterPullBarrelMetrics(
        batter_id="b2",
        batter_name="Weak Flyball Puller",
        flyball_pull_pct=36.0,
        pull_barrel_pct=11.0,
        oppo_barrel_pct=6.0,
        pulled_air_count=65,
        total_bbe_count=210,
    )

    res = engine.evaluate_pull_barrel(popup_batter)

    assert res.power_tier == "HARMLESS_PULL_AIR_POPUP_RISK"
    assert res.is_optimal_crusher is False


def test_pull_barrel_health_check():
    """Verify pull barrel health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Pull Barrel verified" in checks[0].detail
