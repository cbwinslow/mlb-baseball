import pytest

from mlb_baseball.model.evaluation import Prediction, _common_sample, _scores


def test_common_sample_keeps_exactly_one_shared_game_per_model():
    rows = [
        Prediction("1", "a", 0.7, True),
        Prediction("1", "b", 0.6, True),
        Prediction("2", "a", 0.4, False),
    ]

    common = _common_sample(rows, ["a", "b"])

    assert [row.game_instance_key for row in common["a"]] == ["1"]
    assert [row.game_instance_key for row in common["b"]] == ["1"]


def test_scores_count_games_not_snapshots():
    scores = _scores(
        [
            Prediction("1", "a", 0.8, True),
            Prediction("2", "a", 0.2, False),
        ]
    )

    assert scores["games"] == 2
    assert scores["accuracy"] == 1.0
    assert scores["brier"] == pytest.approx(0.04)
