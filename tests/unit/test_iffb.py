"""Unit tests for Pitcher Infield Fly Ball Engine (IFFB-01, ADR-181)."""

from mlb_baseball.model.iffb import (
    InfieldFlyBallEngine,
    PitcherIFFBMetrics,
    health_check,
)


def test_elite_popup_artist_classified_as_elite_inducer():
    """Verify high IFFB% yields ELITE_POPUP_INDUCER and positive surplus runs."""
    engine = InfieldFlyBallEngine()

    popup_ace = PitcherIFFBMetrics(
        pitcher_id="p1",
        pitcher_name="High Velo Top Zone Arm",
        iffb_count=29,
        fb_count=180,
        pa_faced=620,
    )

    res = engine.evaluate_iffb(popup_ace, league_iffb_baseline=9.5)

    assert res.iffb_pct > 15.0
    assert res.iffb_delta_league > 5.0
    assert res.popup_surplus_runs > 2.0
    assert res.popup_tier == "ELITE_POPUP_INDUCER"
    assert res.is_elite_popup_artist is True


def test_warning_track_vulnerable_pitcher_classified_properly():
    """Verify low IFFB% triggers WARNING_TRACK_VULNERABLE."""
    engine = InfieldFlyBallEngine()

    vulnerable = PitcherIFFBMetrics(
        pitcher_id="p2",
        pitcher_name="Low Pop Pitcher",
        iffb_count=7,
        fb_count=175,
        pa_faced=600,
    )

    res = engine.evaluate_iffb(vulnerable, league_iffb_baseline=9.5)

    assert res.iffb_pct < 5.0
    assert res.popup_surplus_runs < -1.5
    assert res.popup_tier == "WARNING_TRACK_VULNERABLE"
    assert res.is_elite_popup_artist is False


def test_iffb_health_check():
    """Verify IFFB health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "IFFB verified" in checks[0].detail
