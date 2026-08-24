"""Unit tests for Hierarchical Neural & Tree Residual Combiner (NEURAL-01, ADR-128)."""

import numpy as np

from mlb_baseball.model.neural import (
    EmbeddingMatrix,
    HierarchicalTreeResidualCombiner,
    NeuralEntityIndices,
    health_check,
)


def test_embedding_matrix_lookup():
    """Verify EmbeddingMatrix returns expected shape and preserves Xavier scale."""
    emb = EmbeddingMatrix(vocab_size=100, embedding_dim=16, random_seed=42)
    vectors = emb.lookup([0, 15, 99])

    assert vectors.shape == (3, 16)
    # Check bounded values
    assert np.all(vectors >= -1.0) and np.all(vectors <= 1.0)


def test_hierarchical_tree_residual_combiner_forward():
    """Verify forward pass calculates bounded residual and non-linear composite probability."""
    combiner = HierarchicalTreeResidualCombiner(
        continuous_dim=4,
        pitcher_vocab_size=100,
        team_vocab_size=32,
        venue_vocab_size=30,
        embedding_dim=8,
        random_seed=42,
    )

    cont = np.array(
        [
            [0.2, -0.5, 1.2, -0.1],
            [-0.8, 0.4, 0.1, 0.9],
        ]
    )
    entities = [
        NeuralEntityIndices(
            home_starter_idx=10, away_starter_idx=20, home_team_idx=1, away_team_idx=2, venue_idx=5
        ),
        NeuralEntityIndices(
            home_starter_idx=30, away_starter_idx=40, home_team_idx=3, away_team_idx=4, venue_idx=6
        ),
    ]
    tree_priors = [0.60, 0.45]

    results = combiner.forward(cont, entities, tree_priors, game_keys=["game_a", "game_b"])

    assert len(results) == 2
    assert results[0].game_key == "game_a"
    assert results[0].tree_prior_prob == 0.60
    assert -1.5 <= results[0].neural_residual_delta <= 1.5
    assert 0.01 <= results[0].composite_win_prob <= 0.99
    assert "home_starter_norm" in results[0].embedding_norms


def test_neural_health_check():
    """Verify neural combiner health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Neural residual pass verified" in checks[0].detail
