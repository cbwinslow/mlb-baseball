"""Unit tests for pitch arsenal & batter pitch-type matchup Markov modeling (PLN-04, ADR-100)."""

import random

from mlb_baseball.model import markov
from mlb_baseball.model.markov import (
    EMPTY_ZERO_OUTS,
    TERMINAL,
    BaseOutState,
    BatterArsenalProfile,
    Outcome,
    PitchArsenal,
)


def test_compute_arsenal_matchup_edge_exact_math():
    # Pitcher throws 60% Fastball (FF, +1.0 rv/100) and 40% Curveball (CU, +2.0 rv/100)
    pitcher = PitchArsenal(
        player_id="1001",
        season=2024,
        pitch_usage={"FF": 0.60, "CU": 0.40},
        run_values_per_100={"FF": 1.0, "CU": 2.0},
        woba_against={"FF": 0.320, "CU": 0.220},
        whiff_pct={"FF": 0.20, "CU": 0.35},
    )

    # Batter has +3.0 rv/100 vs FF, but -1.0 rv/100 vs CU
    batter = BatterArsenalProfile(
        player_id="2001",
        season=2024,
        pitches_seen={"FF": 500, "CU": 200},
        run_values_per_100={"FF": 3.0, "CU": -1.0},
        woba={"FF": 0.410, "CU": 0.250},
        whiff_pct={"FF": 0.15, "CU": 0.30},
    )

    # Edge = 0.60 * (3.0 - 1.0) + 0.40 * (-1.0 - 2.0)
    #      = 0.60 * 2.0 + 0.40 * (-3.0)
    #      = 1.20 - 1.20 = 0.0
    edge = markov.compute_arsenal_matchup_edge(pitcher, batter)
    assert abs(edge - 0.0) < 1e-9

    # Batter that crushes Curveballs (+4.0 rv/100) and Fastballs (+2.0 rv/100)
    crusher = BatterArsenalProfile(
        player_id="2002",
        season=2024,
        pitches_seen={"FF": 500, "CU": 200},
        run_values_per_100={"FF": 2.0, "CU": 4.0},
        woba={"FF": 0.380, "CU": 0.450},
        whiff_pct={"FF": 0.12, "CU": 0.18},
    )
    # Edge = 0.60 * (2.0 - 1.0) + 0.40 * (4.0 - 2.0) = 0.60 * 1.0 + 0.40 * 2.0 = 1.40
    crusher_edge = markov.compute_arsenal_matchup_edge(pitcher, crusher)
    assert abs(crusher_edge - 1.40) < 1e-9


def test_adjust_outcome_distribution_for_matchup_sums_to_one():
    # Simple base distribution: from EMPTY_ZERO_OUTS,
    # 30% hit (1st/0, 0 runs), 70% out (empty/1, 0 runs)
    state_1st_0 = BaseOutState(0, on1=True)
    state_empty_1 = BaseOutState(1)

    base_dist = {
        EMPTY_ZERO_OUTS: {
            Outcome(state_1st_0, 0): 0.30,
            Outcome(state_empty_1, 0): 0.70,
        },
        state_1st_0: {
            Outcome(TERMINAL, 0): 1.0,
        },
        state_empty_1: {
            Outcome(TERMINAL, 0): 1.0,
        },
    }

    # Batter advantage: +2.0 runs per 100 pitches
    adj_dist = markov.adjust_outcome_distribution_for_matchup(base_dist, edge_runs_per_100=2.0)

    # Check each pre-state distribution still sums to 1.0
    for _pre, outcome_probs in adj_dist.items():
        total_p = sum(outcome_probs.values())
        assert abs(total_p - 1.0) < 1e-9

    # Hit probability from EMPTY_ZERO_OUTS should increase from 0.30
    assert adj_dist[EMPTY_ZERO_OUTS][Outcome(state_1st_0, 0)] > 0.30


def test_simulate_matchup_game_deterministic_with_seed():
    state_1st_0 = BaseOutState(0, on1=True)
    state_empty_1 = BaseOutState(1)
    base_dist = {
        EMPTY_ZERO_OUTS: {
            Outcome(state_1st_0, 0): 0.40,
            Outcome(state_empty_1, 0): 0.60,
        },
        state_1st_0: {
            Outcome(EMPTY_ZERO_OUTS, 1): 0.30,
            Outcome(TERMINAL, 0): 0.70,
        },
        state_empty_1: {
            Outcome(TERMINAL, 0): 1.0,
        },
    }

    rng1 = random.Random(42)
    rng2 = random.Random(42)

    res1 = markov.simulate_matchup_game(
        base_dist, rng1, home_edge_runs_per_100=1.5, away_edge_runs_per_100=-1.0
    )
    res2 = markov.simulate_matchup_game(
        base_dist, rng2, home_edge_runs_per_100=1.5, away_edge_runs_per_100=-1.0
    )

    assert res1 == res2
    assert res1.innings >= 9
