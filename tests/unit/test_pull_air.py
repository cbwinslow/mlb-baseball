"""Unit tests for Batter Pulled-Air Power Engine (PULL-AIR-01, ADR-183)."""

from mlb_baseball.model.pull_air import (
    BatterPullAirMetrics,
    PullAirPowerEngine,
    health_check,
)


def test_pull_air_slugger_classified_as_elite_punisher():
    """Verify high pull-air rate and pull HR share yields ELITE_PULL_AIR_PUNISHER."""
    engine = PullAirPowerEngine()

    paredes = BatterPullAirMetrics(
        batter_id="b1",
        batter_name="Isaac Paredes Archetype",
        pulled_air_count=48,
        total_air_count=115,
        pulled_air_hr=26,
        total_hr=28,
    )

    res = engine.evaluate_pull_air(paredes, league_pull_air_baseline=28.5)

    assert res.pull_air_pct > 40.0
    assert res.padm_multiplier > 1.80
    assert res.strategy_archetype == "ELITE_PULL_AIR_PUNISHER"
    assert res.is_elite_pull_air_hitter is True


def test_all_fields_spray_hitter_classified_properly():
    """Verify low pull-air rate triggers ALL_FIELDS_AIR_SPRAY."""
    engine = PullAirPowerEngine()

    all_fields = BatterPullAirMetrics(
        batter_id="b2",
        batter_name="Oppo Spray Hitter",
        pulled_air_count=21,
        total_air_count=110,
        pulled_air_hr=4,
        total_hr=12,
    )

    res = engine.evaluate_pull_air(all_fields, league_pull_air_baseline=28.5)

    assert res.pull_air_pct < 20.0
    assert res.strategy_archetype == "ALL_FIELDS_AIR_SPRAY"
    assert res.is_elite_pull_air_hitter is False


def test_pull_air_health_check():
    """Verify pull-air health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Pull-air verified" in checks[0].detail
