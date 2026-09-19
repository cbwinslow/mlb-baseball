"""Unit tests for Individual Umpire Strike Zone & Run Bias Modeler (UMP-01, ADR-136)."""

import dataclasses

import pytest

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
        zone_horizontal_expansion_in=0.80,
        run_impact_per_game=-0.50,
        k_rate_multiplier=1.08,
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
        zone_horizontal_expansion_in=-0.60,
        run_impact_per_game=+0.45,
        k_rate_multiplier=0.94,
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


def test_umpire_profile_has_no_fields_unread_by_the_engine():
    """Regression: UmpireProfile used to accept games_behind_plate,
    zone_vertical_expansion_in, called_strike_accuracy_pct, and
    bb_rate_multiplier without evaluate_game_adjustment ever reading them
    (mlb_baseball/metrics/umpire_zone_run_bias.yaml). Every field on the
    dataclass must now be one the engine actually consumes.
    """
    field_names = {f.name for f in dataclasses.fields(UmpireProfile)}
    assert field_names == {
        "umpire_id",
        "umpire_name",
        "zone_horizontal_expansion_in",
        "run_impact_per_game",
        "k_rate_multiplier",
    }


def test_umpire_profile_rejects_the_removed_dead_fields():
    with pytest.raises(TypeError):
        UmpireProfile(
            umpire_id="u1",
            umpire_name="Ghost Field",
            zone_horizontal_expansion_in=0.5,
            run_impact_per_game=0.0,
            k_rate_multiplier=1.0,
            bb_rate_multiplier=1.0,  # type: ignore[call-arg]
        )
