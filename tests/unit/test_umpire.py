"""Unit tests for Individual Umpire Strike Zone & Run Bias Modeler (UMP-01, ADR-136)."""

from mlb_baseball.model.umpire import (
    UmpireBiasEngine,
    UmpireProfile,
    health_check,
)


def test_pitcher_friendly_umpire_run_suppression():
    """Verify pitcher-friendly umpire reduces game total and boosts starter Ks."""
    engine = UmpireBiasEngine()

    ump = UmpireProfile(
        umpire_id="u1",
        umpire_name="Pitcher Pal",
        games_behind_plate=100,
        zone_horizontal_expansion_in=0.80,
        zone_vertical_expansion_in=0.30,
        called_strike_accuracy_pct=92.0,
        run_impact_per_game=-0.50,
        k_rate_multiplier=1.08,
        bb_rate_multiplier=0.90,
    )

    adj = engine.evaluate_game_adjustment(
        ump, baseline_total=9.0, home_starter_base_ks=6.0, away_starter_base_ks=5.0
    )

    assert adj.adjusted_total_runs == 8.50
    assert adj.run_adjustment_delta == -0.50
    assert adj.home_starter_k_line_adjustment == 6.48
    assert adj.away_starter_k_line_adjustment == 5.40
    assert adj.zone_classification == "pitcher_friendly"


def test_hitter_friendly_umpire_run_boost():
    """Verify tight-zone umpire increases game total and suppresses starter Ks."""
    engine = UmpireBiasEngine()

    ump = UmpireProfile(
        umpire_id="u2",
        umpire_name="Tight Zone",
        games_behind_plate=85,
        zone_horizontal_expansion_in=-0.60,
        zone_vertical_expansion_in=-0.20,
        called_strike_accuracy_pct=95.0,
        run_impact_per_game=+0.45,
        k_rate_multiplier=0.94,
        bb_rate_multiplier=1.12,
    )

    adj = engine.evaluate_game_adjustment(ump, baseline_total=8.0, home_starter_base_ks=7.0)

    assert adj.adjusted_total_runs == 8.45
    assert adj.run_adjustment_delta == +0.45
    assert adj.home_starter_k_line_adjustment == 6.58
    assert adj.zone_classification == "hitter_friendly"


def test_umpire_health_check():
    """Verify umpire health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Umpire adjustments verified" in checks[0].detail
