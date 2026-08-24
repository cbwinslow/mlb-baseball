"""Unit tests for Win Expectancy (WE), WPA, and Leverage Index Engine (MATH-01, ADR-115)."""

import pytest

from mlb_baseball.model.wpa import InGameSituation, WinExpectancyEngine, health_check


def test_win_expectancy_pregame_and_terminal():
    """Verify baseline entering win expectancy and terminal state boundary conditions."""
    engine = WinExpectancyEngine()

    # 1. Entering 0-0 in Top 1st
    s_start = InGameSituation(
        inning=1,
        is_bottom_half=False,
        outs=0,
        on1=False,
        on2=False,
        on3=False,
        home_score=0,
        away_score=0,
    )
    we_start = engine.calculate_win_expectancy(s_start)
    assert 0.50 <= we_start <= 0.56

    # 2. Home team leading 7-1 in Top 9th, 2 outs
    s_lead = InGameSituation(
        inning=9,
        is_bottom_half=False,
        outs=2,
        on1=False,
        on2=False,
        on3=False,
        home_score=7,
        away_score=1,
    )
    we_lead = engine.calculate_win_expectancy(s_lead)
    assert we_lead >= 0.99

    # 3. Away team leading 8-2 in Bottom 9th, 2 outs
    s_trail = InGameSituation(
        inning=9,
        is_bottom_half=True,
        outs=2,
        on1=False,
        on2=False,
        on3=False,
        home_score=2,
        away_score=8,
    )
    we_trail = engine.calculate_win_expectancy(s_trail)
    assert we_trail <= 0.01


def test_wpa_and_leverage_index_high_leverage_walkoff():
    """Verify WPA and Leverage Index calculation during high leverage bottom-9th PA."""
    engine = WinExpectancyEngine()

    # Pre-play: Bottom 9th, 2 outs, bases loaded, Home down 4-5
    pre = InGameSituation(
        inning=9,
        is_bottom_half=True,
        outs=2,
        on1=True,
        on2=True,
        on3=True,
        home_score=4,
        away_score=5,
    )
    # Post-play: Walk-off Grand Slam -> Home wins 8-5
    post = InGameSituation(
        inning=9,
        is_bottom_half=True,
        outs=2,
        on1=False,
        on2=False,
        on3=False,
        home_score=8,
        away_score=5,
    )

    result = engine.evaluate_play_transition(pre, post)

    # 1. High leverage index in bottom 9th
    assert result.leverage_index >= 2.0

    # 2. Dramatic positive WPA for home team
    assert result.wpa_home > 0.40
    assert result.wpa_away < -0.40
    assert result.wpa_home + result.wpa_away == pytest.approx(0.0, abs=1e-4)


def test_wpa_health_check():
    """Verify WPA engine operational health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "288-state" in checks[0].detail
