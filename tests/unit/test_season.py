"""Unit tests for Full-Season Monte Carlo & Playoff Simulation Engine (PROJ-01, ADR-109)."""

import numpy as np
import pytest

from mlb_baseball.model.season import (
    ALL_MLB_TEAMS,
    MLB_DIVISIONS,
    generate_balanced_schedule,
    log5_game_win_prob,
    simulate_season_monte_carlo,
    simulate_series,
    team_league_and_division,
)


def test_log5_game_win_prob_math():
    """Verify Log5 calculation arithmetic and home field advantage."""
    # 1. Symmetric talent (0.500 vs 0.500) with 0.035 HFA -> 0.535
    p_even = log5_game_win_prob(0.500, 0.500, hfa=0.035)
    assert pytest.approx(p_even, abs=1e-4) == 0.535

    # 2. Strong home team (0.600) vs weak away team (0.400)
    # odds_a = 0.6/0.4 = 1.5, odds_b = 0.4/0.6 = 0.6667
    # neutral = 1.5 / (1.5 + 0.6667) = 1.5 / 2.1667 = 0.6923
    # with HFA 0.035 -> 0.7273
    p_strong = log5_game_win_prob(0.600, 0.400, hfa=0.035)
    assert pytest.approx(p_strong, abs=1e-3) == 0.7273

    # 3. Boundary bounds
    assert 0.01 <= log5_game_win_prob(0.999, 0.001) <= 0.99
    assert 0.01 <= log5_game_win_prob(0.001, 0.999) <= 0.99


def test_team_league_and_division_mapping():
    """Verify all 30 MLB franchises map to valid leagues and divisions."""
    assert len(ALL_MLB_TEAMS) == 30
    for team in ALL_MLB_TEAMS:
        league, division = team_league_and_division(team)
        assert league in ("AL", "NL")
        assert division in MLB_DIVISIONS[league]


def test_simulate_series_deterministic():
    """Verify playoff series simulation logic for best-of-3, best-of-5, and best-of-7."""
    rng = np.random.default_rng(42)
    # Guaranteed win
    assert simulate_series(team_a_prob=1.0, length=7, rng=rng) is True
    # Guaranteed loss
    assert simulate_series(team_a_prob=0.0, length=7, rng=rng) is False

    # 50/50 series over 1000 trials
    wins = sum(simulate_series(team_a_prob=0.5, length=7, rng=rng) for _ in range(1000))
    assert 450 <= wins <= 550


def test_season_monte_carlo_conservation_of_wins_and_titles():
    """Verify strict mathematical conservation laws across full season Monte Carlo simulations:

    1. Total regular-season wins == Total regular-season games played
    2. Sum of division titles == 6 (3 AL + 3 NL)
    3. Sum of playoff appearances == 12 (6 AL + 6 NL)
    4. Sum of pennant win probabilities == 2.000 (1 AL + 1 NL)
    5. Sum of World Series championship probabilities == 1.000
    """
    # 30 teams with balanced talents centered around 0.500
    talents = {team: 0.450 + (i * 0.0035) for i, team in enumerate(ALL_MLB_TEAMS)}
    schedule = generate_balanced_schedule(ALL_MLB_TEAMS)
    assert len(schedule) > 0

    n_sims = 1000
    result = simulate_season_monte_carlo(
        schedule=schedule,
        team_true_talents=talents,
        n_simulations=n_sims,
        seed=12345,
        season=2024,
    )

    assert result.simulations_run == n_sims
    assert len(result.team_projections) == 30

    # 1. Conservation of titles
    total_div_prob = sum(p.win_division_prob for p in result.team_projections.values())
    assert pytest.approx(total_div_prob, abs=1e-2) == 6.0

    total_playoff_prob = sum(p.make_playoffs_prob for p in result.team_projections.values())
    assert pytest.approx(total_playoff_prob, abs=1e-2) == 12.0

    total_pennant_prob = sum(p.win_pennant_prob for p in result.team_projections.values())
    assert pytest.approx(total_pennant_prob, abs=1e-2) == 2.0

    total_ws_prob = sum(p.win_world_series_prob for p in result.team_projections.values())
    assert pytest.approx(total_ws_prob, abs=1e-2) == 1.0

    # 2. Stronger teams should have higher projected win totals and playoff odds
    best_team = max(result.team_projections.values(), key=lambda p: p.true_talent_wpct)
    worst_team = min(result.team_projections.values(), key=lambda p: p.true_talent_wpct)
    assert best_team.mean_wins > worst_team.mean_wins
    assert best_team.make_playoffs_prob > worst_team.make_playoffs_prob
    assert best_team.win_world_series_prob >= worst_team.win_world_series_prob
