"""Regression and provenance integration coverage for mlb_baseball.model.gbm.

MODEL_DIR is monkeypatched to a tmp_path location in tests here so test
training never pollutes real models/ or real database tables.
"""

import random
from decimal import Decimal

from mlb_baseball.model import gbm, provenance


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("UPDATE gold.prediction SET model_id = NULL, model_run_id = NULL")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM meta.model_run")
        cur.execute("DELETE FROM meta.model")
    db_conn.commit()


def _seed_synthetic_games(db_conn, season: int, count: int, start_pk: int, decided: bool = True):
    rng = random.Random(season)
    rows = []
    for i in range(count):
        home_elo = 1400 + rng.random() * 200
        away_elo = 1400 + rng.random() * 200
        home_win = (home_elo > away_elo) if decided else None
        rows.append(
            (
                f"{start_pk + i}",
                f"test:{start_pk + i}",
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
            "(mlb_game_pk, game_instance_key, season, game_date, home_win_pct, away_win_pct, "
            "home_win_pct_10, away_win_pct_10, home_run_diff, away_run_diff, "
            "home_pyth_wpct, away_pyth_wpct, home_elo, away_elo, home_win) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            rows,
        )
    db_conn.commit()


def test_train_produces_metrics_and_saves_when_it_beats_baselines(db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(gbm, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(gbm, "MODEL_PATH", tmp_path / "gbm-v1.json")
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

    artifacts = list((tmp_path / "artifacts").glob("*.json"))
    assert len(artifacts) == 1

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT run_type, status FROM meta.model_run WHERE model_id = %s",
            (metrics["model_id"],),
        )
        run = cur.fetchone()
    assert run == ("train", "success")

    _reset(db_conn)


def test_predict_writes_predictions_for_upcoming_games_using_saved_model(
    db_conn, tmp_path, monkeypatch
):
    monkeypatch.setattr(gbm, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(gbm, "MODEL_PATH", tmp_path / "gbm-v1.json")
    monkeypatch.setattr(gbm, "TRAIN_SEASON_CUTOFF", 2020)
    monkeypatch.setattr(gbm, "VALIDATION_SEASONS", (2021,))
    _reset(db_conn)
    _seed_synthetic_games(db_conn, 2020, 300, start_pk=500000)
    _seed_synthetic_games(db_conn, 2021, 100, start_pk=600000)
    gbm.train(db_conn)

    _seed_synthetic_games(db_conn, 2022, 5, start_pk=700000, decided=False)

    inserted = gbm.predict(db_conn)

    assert inserted == 5
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_win_prob, model_version, model_id, model_run_id FROM gold.prediction"
        )
        rows = cur.fetchall()
    assert len(rows) == 5
    for prob, model_version, model_id, model_run_id in rows:
        assert model_version == "gbm-v1"
        assert Decimal("0") <= prob <= Decimal("1")
        assert model_id is not None
        assert model_run_id is not None

    _reset(db_conn)


def test_train_and_predict_tolerate_optional_columns_being_null(db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(gbm, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(gbm, "MODEL_PATH", tmp_path / "gbm-v1.json")
    monkeypatch.setattr(gbm, "TRAIN_SEASON_CUTOFF", 2020)
    monkeypatch.setattr(gbm, "VALIDATION_SEASONS", (2021,))
    _reset(db_conn)
    _seed_synthetic_games(db_conn, 2020, 300, start_pk=500000)
    _seed_synthetic_games(db_conn, 2021, 100, start_pk=600000)

    metrics = gbm.train(db_conn)
    assert metrics["train_rows"] == 300
    assert metrics["validation_rows"] == 100

    _seed_synthetic_games(db_conn, 2022, 5, start_pk=700000, decided=False)
    inserted = gbm.predict(db_conn)
    assert inserted == 5

    _reset(db_conn)


def test_predict_returns_zero_when_no_champion_exists(db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(gbm, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(gbm, "MODEL_PATH", tmp_path / "never-trained.json")
    _reset(db_conn)

    assert gbm.predict(db_conn) == 0


def test_health_check_reports_missing_model_file(tmp_path, monkeypatch):
    monkeypatch.setattr(gbm, "MODEL_DIR", tmp_path / "nonexistent")
    monkeypatch.setattr(gbm, "MODEL_PATH", tmp_path / "never-trained.json")

    check = gbm.health_check()[0]

    assert not check.ok
    assert "mlb train" in check.detail


def test_artifact_immutability(db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(gbm, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(gbm, "MODEL_PATH", tmp_path / "gbm-v1.json")
    monkeypatch.setattr(gbm, "TRAIN_SEASON_CUTOFF", 2020)
    monkeypatch.setattr(gbm, "VALIDATION_SEASONS", (2021,))
    _reset(db_conn)
    _seed_synthetic_games(db_conn, 2020, 300, start_pk=500000)
    _seed_synthetic_games(db_conn, 2021, 100, start_pk=600000)

    gbm.train(db_conn)
    artifacts_dir = tmp_path / "artifacts"
    artifacts = list(artifacts_dir.glob("*.json"))
    assert len(artifacts) == 1

    artifact_file = artifacts[0]
    expected_sha = provenance.artifact_sha256(artifact_file)
    assert artifact_file.name == f"{expected_sha}.json"
    assert not (tmp_path / "gbm-v1.json").exists()

    _reset(db_conn)


def test_champion_replacement(db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(gbm, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(gbm, "MODEL_PATH", tmp_path / "gbm-v1.json")
    _reset(db_conn)

    dummy1 = tmp_path / "dummy1.json"
    dummy2 = tmp_path / "dummy2.json"
    dummy1.write_text("model1_content")
    dummy2.write_text("model2_content")

    id1 = provenance.register_model(
        db_conn,
        name="gbm",
        target="home_win",
        model_version="gbm-v1",
        feature_set_version="game-feature-v1",
        status="champion",
        artifact_path=dummy1,
    )

    id2 = provenance.register_model(
        db_conn,
        name="gbm",
        target="home_win",
        model_version="gbm-v1",
        feature_set_version="game-feature-v1",
        status="champion",
        artifact_path=dummy2,
    )

    with db_conn.cursor() as cur:
        cur.execute("SELECT model_id, status FROM meta.model WHERE name = 'gbm'")
        rows = dict(cur.fetchall())

    assert id1 != id2
    assert rows[id1] == "retired"
    assert rows[id2] == "champion"

    champions = [k for k, v in rows.items() if v == "champion"]
    assert len(champions) == 1
    assert champions[0] == id2

    _reset(db_conn)


def test_prediction_foreign_key_linkage(db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(gbm, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(gbm, "MODEL_PATH", tmp_path / "gbm-v1.json")
    monkeypatch.setattr(gbm, "TRAIN_SEASON_CUTOFF", 2020)
    monkeypatch.setattr(gbm, "VALIDATION_SEASONS", (2021,))
    _reset(db_conn)
    _seed_synthetic_games(db_conn, 2020, 300, start_pk=500000)
    _seed_synthetic_games(db_conn, 2021, 100, start_pk=600000)
    gbm.train(db_conn)

    _seed_synthetic_games(db_conn, 2022, 3, start_pk=700000, decided=False)
    inserted = gbm.predict(db_conn)
    assert inserted == 3

    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.mlb_game_pk, p.model_id, p.model_run_id, m.status, r.run_type, r.status
            FROM gold.prediction p
            JOIN meta.model m ON p.model_id = m.model_id
            JOIN meta.model_run r ON p.model_run_id = r.run_id
            """
        )
        rows = cur.fetchall()

    assert len(rows) == 3
    for _pk, model_id, model_run_id, m_status, r_type, r_status in rows:
        assert model_id is not None
        assert model_run_id is not None
        assert m_status == "champion"
        assert r_type == "predict"
        assert r_status == "success"

    _reset(db_conn)


def test_no_champion_behavior(db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(gbm, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(gbm, "MODEL_PATH", tmp_path / "never-trained.json")
    _reset(db_conn)

    _seed_synthetic_games(db_conn, 2022, 5, start_pk=700000, decided=False)

    inserted = gbm.predict(db_conn)
    assert inserted == 0

    with db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM gold.prediction")
        (pred_count,) = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM meta.model_run")
        (run_count,) = cur.fetchone()

    assert pred_count == 0
    assert run_count == 0

    _reset(db_conn)
