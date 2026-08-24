"""Unit tests for Player Archetype & Similarity Engine (CLUSTER-01, ADR-132)."""

from mlb_baseball.model.cluster import (
    BatterZoneProfiler,
    PitcherRepertoireVector,
    PitcherSimilarityEngine,
    health_check,
)


def test_pitcher_similarity_distance_and_ranking():
    """Verify PitcherSimilarityEngine ranks closest physical twin at #1 with >90% score."""
    engine = PitcherSimilarityEngine()

    target = PitcherRepertoireVector(
        pitcher_id="t1",
        pitcher_name="Spencer Strider",
        season=2024,
        fastball_velo_mph=97.5,
        fastball_ivb_in=19.2,
        slider_sweep_in=-6.5,
        curve_drop_in=-8.0,
        release_extension_ft=6.8,
    )

    twin = PitcherRepertoireVector(
        pitcher_id="c1",
        pitcher_name="Strider 2023",
        season=2023,
        fastball_velo_mph=97.2,
        fastball_ivb_in=19.0,
        slider_sweep_in=-6.8,
        curve_drop_in=-8.2,
        release_extension_ft=6.7,
    )

    crafty_lefty = PitcherRepertoireVector(
        pitcher_id="c2",
        pitcher_name="Crafty Veteran",
        season=2023,
        fastball_velo_mph=88.5,
        fastball_ivb_in=12.0,
        slider_sweep_in=-12.0,
        curve_drop_in=-14.0,
        release_extension_ft=5.6,
    )

    comps = engine.find_pitcher_comps(target, [twin, crafty_lefty], top_k=2)

    assert len(comps) == 2
    assert comps[0].matched_pitcher_id == "c1"
    assert comps[0].similarity_score_pct > 90.0
    assert comps[1].matched_pitcher_id == "c2"
    assert comps[1].similarity_score_pct < 60.0


def test_batter_zone_vulnerability_profiler():
    """Verify BatterZoneProfiler detects high-whiff quadrant."""
    profiler = BatterZoneProfiler()

    # Batter swings at 10 pitches in Quad 3 (Top-Right: px=0.5, pz=3.2), whiffs 9 times
    # Batter swings at 10 pitches in Quad 8 (Bot-Center: px=0.0, pz=1.8), whiffs 1 time
    swings = (
        [(0.5, 3.2, True)] * 9
        + [(0.5, 3.2, False)] * 1
        + [(0.0, 1.8, True)] * 1
        + [(0.0, 1.8, False)] * 9
    )

    prof = profiler.profile_batter("b1", "Free Swinger", swings)

    assert prof.most_vulnerable_zone == 3
    assert prof.cold_zone_whiff_rate == 0.90
    assert prof.zone_whiff_rates[8] == 0.10


def test_cluster_health_check():
    """Verify cluster health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Pitcher comps verified" in checks[0].detail
