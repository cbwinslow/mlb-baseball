"""Unit tests for Real-Time In-Play Live Game Tracker (LIVE-02, ADR-110)."""

import pytest

from mlb_baseball.live import evaluate_live_game_state
from mlb_baseball.model.markov import (
    TERMINAL,
    BaseOutState,
    Outcome,
)
from mlb_baseball.model.simulate import DenseOutcomeTable


@pytest.fixture
def sample_dense_table():
    """Create a deterministic DenseOutcomeTable fixture with realistic run values."""
    dist = {}
    for outs in (0, 1, 2):
        for on1 in (False, True):
            for on2 in (False, True):
                for on3 in (False, True):
                    state = BaseOutState(outs=outs, on1=on1, on2=on2, on3=on3)
                    next_out = outs + 1
                    next_s = (
                        BaseOutState(outs=next_out, on1=on1, on2=on2, on3=on3)
                        if next_out < 3
                        else TERMINAL
                    )
                    # ~72% out, ~23% single (0 runs if bases empty, 1 if occupied), ~5% solo HR
                    dist[state] = {
                        Outcome(next_s, 0): 0.75,
                        Outcome(state, 0): 0.20,
                        Outcome(state, 1): 0.05,
                    }
    return DenseOutcomeTable.from_distribution(dist)


def test_evaluate_live_game_state_in_play(sample_dense_table):
    """Verify in-play evaluation calculates live win probability and final score expectations."""
    game_data = {
        "mlb_game_pk": "712999",
        "game_date": "2024-06-01",
        "home_team": "BOS",
        "away_team": "NYA",
        "home_score": 4,
        "away_score": 2,
        "starter_siera_diff": -0.40,
        "market_home_prob": 0.75,
    }

    snapshot = evaluate_live_game_state(
        game_data=game_data,
        transition_table=sample_dense_table,
        current_inning=8,
        is_bottom_half=False,
        current_outs=1,
        n_simulations=1000,
        seed=42,
    )

    assert snapshot.mlb_game_pk == "712999"
    assert snapshot.home_team == "BOS"
    assert snapshot.away_team == "NYA"
    assert snapshot.current_inning == 8
    assert snapshot.is_bottom_half is False
    assert snapshot.home_score == 4
    assert snapshot.away_score == 2

    # Leading 4-2 in 8th inning -> high win probability (> 75%)
    assert snapshot.home_win_prob > 0.75
    assert snapshot.away_win_prob < 0.25
    assert snapshot.expected_home_runs >= 4.0
    assert snapshot.expected_away_runs >= 2.0
    assert snapshot.market_home_prob == 0.75
    assert snapshot.edge_alpha is not None
    assert snapshot.edge_alpha == pytest.approx(snapshot.home_win_prob - 0.75, abs=1e-4)
