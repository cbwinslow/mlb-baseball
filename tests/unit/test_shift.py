"""Unit tests for Defensive Alignment & Batted Ball Suppression Engine (SHIFT-01, ADR-140)."""

from mlb_baseball.model.shift import (
    AlignmentType,
    BatterBattedBallTendencies,
    DefensiveAlignmentEngine,
    DefensiveAlignmentProfile,
    health_check,
)


def test_shaded_pull_defense_suppresses_pull_hitter():
    """Verify shaded pull defense suppresses BABIP against heavy pull ground-ball hitter."""
    engine = DefensiveAlignmentEngine()

    pull_hitter = BatterBattedBallTendencies(
        batter_id="b1",
        batter_name="Pull Heavy",
        pull_pct_ground_balls=0.55,
        sprint_speed_ft_s=26.5,
    )

    elite_defense = DefensiveAlignmentProfile(
        team_id="lad",
        alignment=AlignmentType.SHADED_PULL,
        infield_oaa_season=10.0,
    )

    res = engine.evaluate_defensive_matchup(elite_defense, pull_hitter)

    assert res.expected_babip < 0.275
    assert res.babip_delta_vs_league < -0.020
    assert res.ground_ball_out_rate > 0.78
    assert res.expected_run_prevention_per_game < -0.20


def test_infield_in_increases_babip():
    """Verify infield in alignment increases ground ball hit rate."""
    engine = DefensiveAlignmentEngine()

    neutral_batter = BatterBattedBallTendencies(
        batter_id="b2",
        batter_name="Neutral",
        pull_pct_ground_balls=0.40,
    )

    infield_in_defense = DefensiveAlignmentProfile(
        team_id="nyy",
        alignment=AlignmentType.INFIELD_IN,
    )

    res = engine.evaluate_defensive_matchup(infield_in_defense, neutral_batter)

    assert res.expected_babip > 0.330
    assert res.ground_ball_out_rate < 0.65


def test_shift_health_check():
    """Verify shift health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Defensive shift verified" in checks[0].detail
