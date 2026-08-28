"""Unit tests for Live In-Game Bullpen Optimizer (BULLPEN-OPT-01, ADR-160)."""

from mlb_baseball.model.bullpen_opt import (
    BullpenOptimizerEngine,
    InGameLeverageSituation,
    RelieverCandidate,
    health_check,
)


def test_high_leverage_lefty_lane_selects_rested_lefty():
    """Verify high-leverage 8th inning facing 3 LHBs selects fresh lefty over fatigued righty."""
    engine = BullpenOptimizerEngine()

    bullpen = [
        RelieverCandidate(
            "r1", "Fresh Lefty Specialist", "L", rest_days=2, pitches_last_3d=12, fip=2.70
        ),
        RelieverCandidate(
            "r2", "Overworked Closer", "R", rest_days=0, pitches_last_3d=50, fip=2.40
        ),
        RelieverCandidate("r3", "Middle Reliever", "R", rest_days=3, pitches_last_3d=0, fip=4.10),
    ]

    situation = InGameLeverageSituation(
        inning=8,
        score_diff=1,
        outs=1,
        leverage_index=2.60,
        upcoming_batters_hand=["L", "L", "L"],
    )

    res = engine.optimize_bullpen(situation, bullpen)

    assert res.top_recommendation.name == "Fresh Lefty Specialist"
    assert res.top_recommendation.rank == 1
    assert res.top_recommendation.matchup_advantage > 0.10


def test_blowout_game_selects_low_leverage_eater():
    """Verify low-leverage blowout situation avoids high fatigue penalties."""
    engine = BullpenOptimizerEngine()

    bullpen = [
        RelieverCandidate("r1", "Ace Closer", "R", rest_days=0, pitches_last_3d=35, fip=2.20),
        RelieverCandidate(
            "r2", "Fresh Long Reliever", "R", rest_days=4, pitches_last_3d=0, fip=3.90
        ),
    ]

    blowout = InGameLeverageSituation(
        inning=7,
        score_diff=8,
        outs=0,
        leverage_index=0.20,
        upcoming_batters_hand=["R", "R", "L"],
    )

    res = engine.optimize_bullpen(blowout, bullpen)

    assert res.top_recommendation.name == "Fresh Long Reliever"


def test_bullpen_opt_health_check():
    """Verify bullpen optimizer health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Optimizer verified" in checks[0].detail
