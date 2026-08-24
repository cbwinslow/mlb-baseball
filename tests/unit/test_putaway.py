"""Unit tests for Pitcher Two-Strike Put-Away Engine (PUTAWAY-01, ADR-176)."""

from mlb_baseball.model.putaway import (
    PitcherPutAwayEngine,
    PitcherPutAwayMetrics,
    health_check,
)


def test_elite_closer_classified_as_elite_strikeout_closer():
    """Verify high putaway rate yields ELITE_STRIKEOUT_CLOSER and positive PASI runs."""
    engine = PitcherPutAwayEngine()

    closer = PitcherPutAwayMetrics(
        pitcher_id="p1",
        pitcher_name="Josh Hader Archetype",
        putaway_pct=0.275,
        two_strike_pitches=600,
        whiff_2strike_pct=0.20,
    )

    res = engine.evaluate_putaway(closer, league_putaway_baseline=0.195)

    assert res.putaway_delta_league > 0.070
    assert res.pasi_runs_saved > 4.5
    assert res.finisher_tier == "ELITE_STRIKEOUT_CLOSER"
    assert res.is_elite_putaway_arm is True


def test_foul_ball_extender_classified_as_extender():
    """Verify low putaway rate triggers FOUL_BALL_EXTENDER and negative PASI runs."""
    engine = PitcherPutAwayEngine()

    extender = PitcherPutAwayMetrics(
        pitcher_id="p2",
        pitcher_name="Soft Toss Starter",
        putaway_pct=0.145,
        two_strike_pitches=550,
        whiff_2strike_pct=0.09,
    )

    res = engine.evaluate_putaway(extender, league_putaway_baseline=0.195)

    assert res.putaway_delta_league < -0.040
    assert res.pasi_runs_saved < -2.0
    assert res.finisher_tier == "FOUL_BALL_EXTENDER"
    assert res.is_elite_putaway_arm is False


def test_putaway_health_check():
    """Verify putaway health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Put-away verified" in checks[0].detail
