"""Unit tests for Dynamic Rest-of-Season (ROS) & Playoff Odds Engine (ROS-01, ADR-120)."""

from unittest.mock import MagicMock

import pytest

from mlb_baseball.model.ros import (
    RestOfSeasonSimulator,
    TeamStanding,
    calculate_magic_number,
    health_check,
)


def test_calculate_magic_number_arithmetic():
    """Verify Magic Number arithmetic for division races and clinching."""
    # 1. Standard race: Leader 90-50, 2nd place 82-58
    # (162 + 1) - 90 - 58 = 163 - 148 = 15
    mn = calculate_magic_number(leader_wins=90, trailer_losses=58, total_season_games=162)
    assert mn == 15

    # 2. Tight late-season race: Leader 95-60, 2nd place 92-63
    # 163 - 95 - 63 = 5
    mn2 = calculate_magic_number(leader_wins=95, trailer_losses=63, total_season_games=162)
    assert mn2 == 5

    # 3. Clinched division: 163 - 100 - 65 = -2 -> 0
    mn_clinched = calculate_magic_number(leader_wins=100, trailer_losses=65, total_season_games=162)
    assert mn_clinched == 0


def test_team_standing_dataclass_and_pythagorean():
    """Verify TeamStanding properties and Pythagorean expectation."""
    standing = TeamStanding(
        team_id=1,
        retro_team_id="NYA",
        league="AL",
        division="AL East",
        current_wins=60,
        current_losses=40,
        runs_for=520,
        runs_against=420,
    )

    assert standing.total_games == 100
    assert pytest.approx(standing.win_pct, abs=1e-4) == 0.6000
    assert 0.5800 < standing.pyth_win_pct < 0.6200


def test_simulate_ros_with_mock_db():
    """Verify Rest-of-Season simulation outputs all 30 teams with coherent playoff odds."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur

    # Mock 10 completed games and 10 remaining games
    completed = [
        {
            "id": 1,
            "game_date": "2024-05-01",
            "home_team_id": 1,
            "home_team": "NYA",
            "away_team_id": 2,
            "away_team": "BOS",
            "home_score": 6,
            "away_score": 3,
        }
    ]
    remaining = [
        {
            "id": 2,
            "game_date": "2024-08-02",
            "home_team_id": 1,
            "home_team": "NYA",
            "away_team_id": 2,
            "away_team": "BOS",
        }
    ]

    mock_cur.fetchall.side_effect = [completed, remaining]

    simulator = RestOfSeasonSimulator(random_seed=42)
    report = simulator.simulate_ros(
        season=2024,
        as_of_date="2024-08-01",
        n_sims=50,
        conn=mock_conn,
    )

    assert report.season == 2024
    assert report.as_of_date == "2024-08-01"
    assert report.simulations_count == 50
    assert len(report.team_projections) == 30

    for p in report.team_projections:
        assert p.proj_total_wins_mean >= p.current_wins
        assert 0.0 <= p.division_title_prob <= 1.0
        assert 0.0 <= p.make_playoffs_prob <= 1.0
        assert 0.0 <= p.world_series_prob <= 1.0


def test_ros_health_check():
    """Verify rest-of-season health check passes cleanly."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Magic number" in checks[0].detail
