"""Unit tests for Batter Contact Blast Angle Engine (BLAST-ANGLE-01, ADR-199)."""

from mlb_baseball.model.blast_angle import (
    BatterBlastAngleEngine,
    BatterBlastAngleMetrics,
    health_check,
)


def test_precision_crusher_classified_as_precision_power_blaster():
    """Verify tight launch angle variance and high blast rate yields PRECISION_POWER_BLASTER."""
    engine = BatterBlastAngleEngine()

    alvarez = BatterBlastAngleMetrics(
        batter_id="b1",
        batter_name="Yordan Alvarez Archetype",
        mean_launch_angle_deg=16.5,
        launch_angle_std_deg=19.0,
        sweet_spot_pct=46.0,
        power_blast_window_pct=29.0,
        hard_hit_pct=58.0,
        bbe_count=280,
    )

    res = engine.evaluate_blast_angle(alvarez)

    assert res.lwts_score > 125.0
    assert res.basd_runs_saved > 10.0
    assert res.launch_tier == "PRECISION_POWER_BLASTER"
    assert res.is_precision_blaster is True


def test_erratic_flyball_hitter_triggers_popup_risk_tier():
    """Verify wide launch angle dispersion triggers ERRATIC_FLYBALL_POPUP_RISK."""
    engine = BatterBlastAngleEngine()

    popup_hitter = BatterBlastAngleMetrics(
        batter_id="b2",
        batter_name="Erratic Flyball Hitter",
        mean_launch_angle_deg=28.0,
        launch_angle_std_deg=36.0,
        sweet_spot_pct=26.0,
        power_blast_window_pct=11.0,
        hard_hit_pct=30.0,
        bbe_count=190,
    )

    res = engine.evaluate_blast_angle(popup_hitter)

    assert res.lwts_score < 80.0
    assert res.basd_runs_saved < 0.0
    assert res.launch_tier == "ERRATIC_FLYBALL_POPUP_RISK"
    assert res.is_precision_blaster is False


def test_blast_angle_health_check():
    """Verify blast angle health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Blast angle verified" in checks[0].detail
