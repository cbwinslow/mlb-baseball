"""Unit tests for Doubleheader & Travel Fatigue Engine (TRAVEL-01, ADR-149)."""

from mlb_baseball.model.travel import (
    TeamTravelScheduleState,
    TravelFatigueEngine,
    health_check,
)


def test_cross_country_doubleheader_game2_causes_severe_fatigue():
    """Verify team with 3 TZ shift, short rest, and DH Game 2 reaches SEVERE fatigue."""
    engine = TravelFatigueEngine()

    exhausted = TeamTravelScheduleState(
        team_id="nyy",
        team_abbrev="NYY",
        time_zones_crossed=3,
        hours_of_rest_between_games=12.0,
        is_doubleheader_game_2=True,
        consecutive_game_days=13,
    )

    res = engine.assess_travel_fatigue(exhausted)

    assert res.fatigue_tier == "SEVERE"
    assert res.fatigue_index > 75.0
    assert res.woba_drag_pct < -3.5
    assert res.pitcher_fip_penalty > 0.30


def test_well_rested_home_team_is_fresh():
    """Verify team with no travel and standard rest is classified as FRESH."""
    engine = TravelFatigueEngine()

    fresh = TeamTravelScheduleState(
        team_id="lad",
        team_abbrev="LAD",
        time_zones_crossed=0,
        hours_of_rest_between_games=24.0,
        is_doubleheader_game_2=False,
        consecutive_game_days=3,
    )

    res = engine.assess_travel_fatigue(fresh)

    assert res.fatigue_tier == "FRESH"
    assert res.fatigue_index == 0.0
    assert res.woba_drag_pct == 0.0
    assert res.pitcher_fip_penalty == 0.0


def test_travel_health_check():
    """Verify travel health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Travel verified" in checks[0].detail
