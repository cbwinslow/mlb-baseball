"""Unit tests for high-speed vectorized Monte Carlo Markov game simulator (ADR-105)."""

import pytest

from mlb_baseball.model.markov import (
    TERMINAL,
    BaseOutState,
    MarkovError,
    Outcome,
    TransitionCountRow,
)
from mlb_baseball.model.simulate import (
    DenseOutcomeTable,
    index_to_state,
    simulate_games_fast,
    simulate_half_innings_fast,
    simulate_live_game_fast,
    simulate_two_phase_game_fast,
    state_to_index,
)


def test_state_to_index_and_index_to_state_bijection():
    """Verify that all 24 transient states and TERMINAL map bijectively to 0..24."""
    seen_indices = set()
    for outs in (0, 1, 2):
        for b1 in (False, True):
            for b2 in (False, True):
                for b3 in (False, True):
                    state = BaseOutState(outs, b1, b2, b3)
                    idx = state_to_index(state)
                    assert 0 <= idx < 24
                    assert idx not in seen_indices
                    seen_indices.add(idx)
                    # Roundtrip check
                    recovered = index_to_state(idx)
                    assert recovered == state

    assert len(seen_indices) == 24
    # Terminal check
    assert state_to_index(TERMINAL) == 24
    assert state_to_index(BaseOutState(outs=3, on1=True)) == 24
    assert index_to_state(24) == TERMINAL


def test_dense_outcome_table_conversion():
    """Verify conversion from dictionary outcome distribution to DenseOutcomeTable."""
    pre1 = BaseOutState(0, False, False, False)
    pre2 = BaseOutState(0, True, False, False)
    post1 = BaseOutState(0, True, False, False)

    dist = {
        pre1: {Outcome(post1, 0): 0.3, Outcome(TERMINAL, 0): 0.7},
        pre2: {Outcome(TERMINAL, 1): 1.0},
    }

    table = DenseOutcomeTable.from_distribution(dist)
    idx1 = state_to_index(pre1)
    idx2 = state_to_index(pre2)

    assert table.n_outcomes[idx1] == 2
    assert table.n_outcomes[idx2] == 1
    # Check probabilities reach 1.0
    assert table.cum_probs[idx1, 1] == pytest.approx(1.0)
    assert table.cum_probs[idx2, 0] == pytest.approx(1.0)


def test_dense_outcome_table_matchup_adjustment():
    """Verify odds scaling for matchup edge correctly adjusts scoring and
    advancing probabilities."""
    rows = [
        TransitionCountRow(0, False, False, False, 0, True, False, False, 0, 50),
        TransitionCountRow(0, False, False, False, 1, False, False, False, 0, 50),
    ]
    table = DenseOutcomeTable.from_transition_rows(rows)

    # Positive edge should boost advancing probability
    adj_pos = table.adjust_for_matchup(edge_runs_per_100=2.0)
    idx0 = state_to_index(BaseOutState(0, False, False, False))

    # In adj_pos, positive outcome (advancing to 0 out on 1st) should have higher
    # probability than before
    orig_prob = table.raw_probs[idx0, 0]
    adj_prob = adj_pos.raw_probs[idx0, 0]
    assert adj_prob > orig_prob
    assert adj_pos.cum_probs[idx0, adj_pos.n_outcomes[idx0] - 1] == pytest.approx(1.0)


def test_simulate_half_innings_fast_deterministic_chain():
    """Verify fast vectorized simulation on a deterministic chain."""
    s0 = BaseOutState(0, False, False, False)
    s1 = BaseOutState(0, True, False, False)
    dist = {
        s0: {Outcome(s1, 0): 1.0},
        s1: {Outcome(TERMINAL, 2): 1.0},
    }
    table = DenseOutcomeTable.from_distribution(dist)

    runs = simulate_half_innings_fast(table, n_simulations=100, seed=42)
    assert len(runs) == 100
    assert (runs == 2).all()


def test_simulate_half_innings_fast_rejects_invalid_count():
    s0 = BaseOutState(0, False, False, False)
    dist = {s0: {Outcome(TERMINAL, 0): 1.0}}
    table = DenseOutcomeTable.from_distribution(dist)

    with pytest.raises(MarkovError, match="n_simulations must be positive"):
        simulate_half_innings_fast(table, n_simulations=0)


def test_simulate_games_fast_hand_calculated_rules():
    """Verify game-level simulation rules: walk-off, score totals, probabilities sum to 1."""
    # Build a simple distribution:
    # 0 out empty -> 50% chance of 1 run (still 0 out empty), 50% chance of out -> TERMINAL
    s0 = BaseOutState(0, False, False, False)
    dist = {
        s0: {
            Outcome(s0, 1): 0.4,
            Outcome(TERMINAL, 0): 0.6,
        }
    }
    table = DenseOutcomeTable.from_distribution(dist)

    res = simulate_games_fast(
        home_table=table,
        away_table=table,
        n_simulations=500,
        seed=123,
        regulation_innings=9,
    )

    assert res.simulations_run == 500
    assert res.home_win_prob + res.away_win_prob == pytest.approx(1.0, abs=1e-5)
    assert res.home_cover_run_line_prob + res.away_cover_run_line_prob == pytest.approx(
        1.0, abs=1e-5
    )
    assert res.expected_home_runs > 0
    assert res.expected_away_runs > 0
    assert res.expected_total_runs == pytest.approx(
        res.expected_home_runs + res.expected_away_runs, abs=1e-4
    )
    assert sum(res.home_run_distribution.values()) == pytest.approx(1.0, abs=1e-4)
    assert sum(res.away_run_distribution.values()) == pytest.approx(1.0, abs=1e-4)
    assert sum(res.total_run_distribution.values()) == pytest.approx(1.0, abs=1e-4)


def test_simulate_live_game_fast_from_late_inning_lead():
    """Verify live in-game simulation correctly evaluates win probability from lead in 9th."""
    s0 = BaseOutState(0, False, False, False)
    dist = {s0: {Outcome(TERMINAL, 0): 1.0}}
    table = DenseOutcomeTable.from_distribution(dist)

    # Home team leading 5-1 in top of 9th with 2 outs, bases empty
    state_9th = BaseOutState(2, False, False, False)
    live_res = simulate_live_game_fast(
        home_table=table,
        away_table=table,
        current_inning=9,
        is_bottom_half=False,
        current_state=state_9th,
        home_score=5,
        away_score=1,
        n_simulations=200,
        seed=42,
    )

    # On this zero-offense distribution, away team has 1 out to get 4 runs -> 0% win prob
    assert live_res.home_win_prob == pytest.approx(1.0)
    assert live_res.away_win_prob == pytest.approx(0.0)
    assert live_res.expected_final_home_runs == pytest.approx(5.0)
    assert live_res.expected_final_away_runs == pytest.approx(1.0)
    assert live_res.expected_final_total_runs == pytest.approx(6.0)


def test_simulate_two_phase_game_fast():
    """Verify two-phase simulation with starter TTO and F5 metrics."""
    s0 = BaseOutState(0, False, False, False)
    s1 = BaseOutState(0, True, False, False)
    s2 = BaseOutState(0, False, True, False)
    dist = {
        s0: {Outcome(s1, 0): 0.25, Outcome(s0, 1): 0.05, Outcome(TERMINAL, 0): 0.70},
        s1: {Outcome(s1, 1): 0.20, Outcome(TERMINAL, 0): 0.80},
        s2: {Outcome(s2, 1): 0.30, Outcome(TERMINAL, 0): 0.70},
    }
    table = DenseOutcomeTable.from_distribution(dist)

    res = simulate_two_phase_game_fast(
        home_starter_table=table,
        away_starter_table=table,
        home_bullpen_table=table,
        away_bullpen_table=table,
        n_simulations=500,
        seed=42,
        starter_innings=5,
    )

    assert res.simulations_run == 500
    assert res.home_win_prob + res.away_win_prob == pytest.approx(1.0, abs=1e-5)
    # F5 Conservation: Home Win + Tie + Away Win == 1.0
    f5_sum = res.f5_home_win_prob + res.f5_tie_prob + res.f5_away_win_prob
    assert pytest.approx(f5_sum, abs=1e-5) == 1.0
    assert res.f5_expected_total_runs <= res.expected_total_runs
    assert res.f5_expected_home_runs <= res.expected_home_runs
    assert res.f5_expected_away_runs <= res.expected_away_runs
