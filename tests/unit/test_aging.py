"""Unit tests for Skill Aging Projection Engine (AGE-02, ADR-145)."""

from mlb_baseball.model.aging import (
    PlayerTalentBaseline,
    SkillAgingProjectionEngine,
    health_check,
)


def test_pitcher_velocity_decay_after_age_27():
    """Verify pitcher velocity decays systematically after age 27."""
    engine = SkillAgingProjectionEngine()

    veteran_pitcher = PlayerTalentBaseline(
        player_id="p1",
        player_name="Veteran Arm",
        current_age=28.0,
        is_pitcher=True,
        fastball_velo_mph=96.0,
        woba_or_fip=3.40,
    )

    proj = engine.project_multi_year_trajectory(veteran_pitcher, horizon_years=3)

    assert len(proj) == 3
    assert proj[0].projected_age == 29.0
    assert proj[0].projected_fastball_velo_mph < 96.0
    assert proj[2].projected_fastball_velo_mph < proj[0].projected_fastball_velo_mph
    assert proj[2].projected_woba_or_fip > 3.40  # FIP increases (worsens)


def test_young_batter_ascends_to_prime():
    """Verify young 22-year-old batter improves wOBA across next 2 years."""
    engine = SkillAgingProjectionEngine()

    young_batter = PlayerTalentBaseline(
        player_id="b1",
        player_name="Young Phenom",
        current_age=22.0,
        is_pitcher=False,
        woba_or_fip=0.330,
    )

    proj = engine.project_multi_year_trajectory(young_batter, horizon_years=2)

    assert proj[0].projected_woba_or_fip > 0.330
    assert proj[1].projected_woba_or_fip > proj[0].projected_woba_or_fip


def test_aging_health_check():
    """Verify aging health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Aging verified" in checks[0].detail
