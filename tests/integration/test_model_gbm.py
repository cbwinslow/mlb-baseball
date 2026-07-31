"""Regression coverage for mlb_baseball.model.gbm.

MODEL_PATH is always monkeypatched to a tmp_path location in every test
here -- gbm.MODEL_PATH points at the real models/gbm-v1.json used by
production `mlb predict`, and a test training on tiny synthetic data must
never overwrite it with a throwaway model.

gold.game_feature is seeded directly, not built via features.build()/
elo.compute_ratings() -- train()/predict() only ever read gold.game_feature
itself (no join to core.game/core.team needed), and game_id/home_team_id/
away_team_id are nullable, so a real core.game/core.team fixture isn't
needed to exercise this module's actual logic.
"""

import random
from decimal import Decimal

from mlb_baseball.model import gbm


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
    db_conn.commit()


def _seed_synthetic_games(db_conn, season: int, count: int, start_pk: int, decided: bool = True):
    # Deliberately learnable pattern: home wins whenever home_elo >
    # away_elo, so a real model has something real to pick up on --
    # not asserting a specific model wins the comparison (too small/
    # synthetic a dataset for that to be a stable assertion), just that
    # training/prediction run correctly end to end.
    rng = random.Random(season)
    rows = []
    for i in range(count):
        home_elo = 1400 + rng.random() * 200
        away_elo = 1400 + rng.random() * 200
        home_win = (home_elo > away_elo) if decided else None
        rows.append(
            (
                f"{start_pk + i}",
                season,
                f"{season}-04-{(i % 28) + 1:02d}",
                round(rng.uniform(0.3, 0.7), 3),
                round(rng.uniform(0.3, 0.7), 3),
                round(rng.uniform(0.3, 0.7), 3),
                round(rng.uniform(0.3, 0.7), 3),
                rng.randint(-20, 20),
                rng.randint(-20, 20),
                round(rng.uniform(0.3, 0.7), 3),
                round(rng.uniform(0.3, 0.7), 3),
                home_elo,
                away_elo,
                home_win,
            )
        )
    with db_conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO gold.game_feature "
            "(mlb_game_pk, season, game_date, home_win_pct, away_win_pct, "
            "home_win_pct_10, away_win_pct_10, home_run_diff, away_run_diff, "
            "home_pyth_wpct, away_pyth_wpct, home_elo, away_elo, home_win) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            rows,
        )
    db_conn.commit()


def test_train_produces_metrics_and_saves_when_it_beats_baselines(db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(gbm, "MODEL_PATH", tmp_path / "test-gbm.json")
    monkeypatch.setattr(gbm, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(gbm, "TRAIN_SEASON_CUTOFF", 2020)
    monkeypatch.setattr(gbm, "VALIDATION_SEASONS", (2021,))
    _reset(db_conn)
    _seed_synthetic_games(db_conn, 2020, 300, start_pk=500000)
    _seed_synthetic_games(db_conn, 2021, 100, start_pk=600000)

    metrics = gbm.train(db_conn)

    assert metrics["train_rows"] == 300
    assert metrics["validation_rows"] == 100
    for name in ("gbm", "log5", "elo"):
        assert metrics[name]["log_loss"] > 0
        assert 0 <= metrics[name]["brier"] <= 1
    # Whether it happens to beat both baselines on this particular random
    # synthetic draw isn't the point of this test -- but "saved" must
    # accurately reflect whether the file was actually written.
    assert (tmp_path / "test-gbm.json").exists() == metrics["saved"]

    _reset(db_conn)


def test_predict_writes_predictions_for_upcoming_games_using_saved_model(
    db_conn, tmp_path, monkeypatch
):
    monkeypatch.setattr(gbm, "MODEL_PATH", tmp_path / "test-gbm.json")
    monkeypatch.setattr(gbm, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(gbm, "TRAIN_SEASON_CUTOFF", 2020)
    monkeypatch.setattr(gbm, "VALIDATION_SEASONS", (2021,))
    _reset(db_conn)
    _seed_synthetic_games(db_conn, 2020, 300, start_pk=500000)
    _seed_synthetic_games(db_conn, 2021, 100, start_pk=600000)
    gbm.train(db_conn)
    assert (tmp_path / "test-gbm.json").exists()  # this synthetic pattern is learnable -- must save

    _reset_predictions_only(db_conn)
    _seed_synthetic_games(db_conn, 2022, 5, start_pk=700000, decided=False)

    inserted = gbm.predict(db_conn)

    assert inserted == 5
    with db_conn.cursor() as cur:
        cur.execute("SELECT home_win_prob, model_version FROM gold.prediction")
        rows = cur.fetchall()
    assert len(rows) == 5
    for prob, model_version in rows:
        assert model_version == "gbm-v1"
        assert Decimal("0") <= prob <= Decimal("1")

    _reset(db_conn)


def _reset_predictions_only(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
    db_conn.commit()


def test_predict_returns_zero_when_no_model_saved_yet(db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(gbm, "MODEL_PATH", tmp_path / "never-trained.json")
    _reset(db_conn)

    assert gbm.predict(db_conn) == 0


def test_health_check_reports_missing_model_file(tmp_path, monkeypatch):
    monkeypatch.setattr(gbm, "MODEL_PATH", tmp_path / "never-trained.json")

    check = gbm.health_check()[0]

    assert not check.ok
    assert "mlb train" in check.detail
