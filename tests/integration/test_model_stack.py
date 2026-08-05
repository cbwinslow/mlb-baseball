"""Regression coverage for mlb_baseball.model.stack's DB-facing pieces
(train/predict/health_check) -- pure feature-construction logic is
unit-tested in tests/unit/test_stack_formula.py.

MODEL_PATH is always monkeypatched to a tmp_path location -- stack.MODEL_PATH
points at the real models/stack-v1.json used by production `mlb predict`,
and a test training on synthetic data must never overwrite it.

gold.prediction is seeded directly (not via log5.predict()/elo.predict()/
gbm.predict()) so each test controls exactly which (game, model_version,
generated_at) rows exist -- including deliberately stale, superseded rows,
the shape needed to prove the "predict once per game, not once per stale
row" dedup logic actually works (see stack.py's own docstring).
"""

import math
import random
from datetime import datetime, timedelta
from decimal import Decimal

from mlb_baseball.model import stack


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def _seed_teams(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 2025, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147) "
            "RETURNING id, retro_team_id"
        )
        return {retro_id: team_id for team_id, retro_id in cur.fetchall()}


def _seed_decided_game(db_conn, game_pk, game_date, atl, nya, home_win):
    home_score, away_score = (5, 3) if home_win else (3, 5)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, game_pk, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) "
            "VALUES (%s, %s, 2024, %s, %s, %s, %s, %s, 'regular')",
            (f"G{game_pk}", game_pk, game_date, atl, nya, home_score, away_score),
        )


def _seed_prediction(db_conn, game_pk, model_version, home_win_prob, actual_home_win, generated_at):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gold.prediction "
            "(mlb_game_pk, model_version, home_win_prob, actual_home_win, generated_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (game_pk, model_version, home_win_prob, actual_home_win, generated_at),
        )


def _seed_synthetic_stack_games(db_conn, atl, nya, count, start_pk, seed=42):
    """Deliberately learnable via *averaging*, not any single model: each
    of log5/elo/gbm is an independent noisy sigmoid read of the same
    hidden true_strength, noisy enough that no individual model is very
    good, but a linear combination (what logistic regression learns)
    should cancel out a meaningful share of that independent noise --
    exactly the textbook case stacking is supposed to help with. Not
    asserting a specific real-world result (this project doesn't force a
    win narrative from a model, see ADR log), just exercising the
    "beats all three, gets saved" path with a synthetic scenario honestly
    built to make that outcome likely, confirmed deterministic via a
    fixed seed."""
    rng = random.Random(seed)
    base_date = datetime(2024, 4, 1)
    for i in range(count):
        game_pk = f"{start_pk + i}"
        game_date = (base_date + timedelta(days=i)).date().isoformat()
        true_strength = rng.gauss(0, 1.5)
        home_win = true_strength > 0

        def _noisy_prob(strength: float, noise_std: float = 2.0) -> float:
            z = strength + rng.gauss(0, noise_std)
            return 1.0 / (1.0 + math.exp(-z))

        _seed_decided_game(db_conn, game_pk, game_date, atl, nya, home_win)
        generated_at = base_date + timedelta(days=i, hours=1)
        _seed_prediction(
            db_conn, game_pk, "log5-v1", _noisy_prob(true_strength), home_win, generated_at
        )
        _seed_prediction(
            db_conn, game_pk, "elo-v1", _noisy_prob(true_strength), home_win, generated_at
        )
        _seed_prediction(
            db_conn, game_pk, "gbm-v1", _noisy_prob(true_strength), home_win, generated_at
        )
    db_conn.commit()


def test_train_dedupes_to_the_latest_prediction_per_game_and_model(db_conn, tmp_path, monkeypatch):
    # A stale, superseded prediction (earlier generated_at, wildly
    # different probability) must not be what train() sees -- only the
    # latest row per (game, model_version) should ever be used. Confirmed
    # against real production this matters: log5-v1/elo-v1/gbm-v1 average
    # well over 10 raw gold.prediction rows per distinct game.
    monkeypatch.setattr(stack, "MODEL_PATH", tmp_path / "test-stack.json")
    monkeypatch.setattr(stack, "MODEL_DIR", tmp_path)
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    _seed_decided_game(db_conn, "1", "2024-04-01", atl, nya, home_win=True)
    early = datetime(2024, 4, 1, 6, 0)
    late = datetime(2024, 4, 1, 18, 0)
    # Stale rows: home team looked like a big underdog earlier in the day.
    _seed_prediction(db_conn, "1", "log5-v1", Decimal("0.10"), True, early)
    _seed_prediction(db_conn, "1", "elo-v1", Decimal("0.10"), True, early)
    _seed_prediction(db_conn, "1", "gbm-v1", Decimal("0.10"), True, early)
    # Latest rows: the ones that should actually be used.
    _seed_prediction(db_conn, "1", "log5-v1", Decimal("0.90"), True, late)
    _seed_prediction(db_conn, "1", "elo-v1", Decimal("0.90"), True, late)
    _seed_prediction(db_conn, "1", "gbm-v1", Decimal("0.90"), True, late)
    db_conn.commit()

    rows = stack._fetch_training_rows(db_conn)

    assert len(rows) == 1
    _game_date, actual, log5_prob, elo_prob, gbm_prob, poly_prob, kalshi_prob = rows[0]
    assert actual is True
    assert float(log5_prob) == 0.90
    assert float(elo_prob) == 0.90
    assert float(gbm_prob) == 0.90
    assert poly_prob is None
    assert kalshi_prob is None

    _reset(db_conn)


def test_train_requires_all_three_base_models_to_have_a_prediction(db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(stack, "MODEL_PATH", tmp_path / "test-stack.json")
    monkeypatch.setattr(stack, "MODEL_DIR", tmp_path)
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    now = datetime(2024, 4, 1, 12, 0)
    # Game 1: all three -- qualifies.
    _seed_decided_game(db_conn, "1", "2024-04-01", atl, nya, home_win=True)
    _seed_prediction(db_conn, "1", "log5-v1", Decimal("0.6"), True, now)
    _seed_prediction(db_conn, "1", "elo-v1", Decimal("0.6"), True, now)
    _seed_prediction(db_conn, "1", "gbm-v1", Decimal("0.6"), True, now)
    # Game 2: missing gbm-v1 entirely -- must be excluded.
    _seed_decided_game(db_conn, "2", "2024-04-02", atl, nya, home_win=False)
    _seed_prediction(db_conn, "2", "log5-v1", Decimal("0.4"), False, now)
    _seed_prediction(db_conn, "2", "elo-v1", Decimal("0.4"), False, now)
    db_conn.commit()

    rows = stack._fetch_training_rows(db_conn)

    assert len(rows) == 1

    _reset(db_conn)


def test_train_includes_market_columns_only_when_present(db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(stack, "MODEL_PATH", tmp_path / "test-stack.json")
    monkeypatch.setattr(stack, "MODEL_DIR", tmp_path)
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    now = datetime(2024, 4, 1, 12, 0)
    _seed_decided_game(db_conn, "1", "2024-04-01", atl, nya, home_win=True)
    _seed_prediction(db_conn, "1", "log5-v1", Decimal("0.6"), True, now)
    _seed_prediction(db_conn, "1", "elo-v1", Decimal("0.6"), True, now)
    _seed_prediction(db_conn, "1", "gbm-v1", Decimal("0.6"), True, now)
    _seed_prediction(db_conn, "1", "polymarket-v1", Decimal("0.65"), True, now)
    db_conn.commit()

    rows = stack._fetch_training_rows(db_conn)

    assert len(rows) == 1
    *_rest, poly_prob, kalshi_prob = rows[0]
    assert poly_prob == Decimal("0.65")
    assert kalshi_prob is None  # never recorded -- must stay NULL, not error

    _reset(db_conn)


def test_train_raises_a_clear_error_when_too_few_games_qualify(db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(stack, "MODEL_PATH", tmp_path / "test-stack.json")
    monkeypatch.setattr(stack, "MODEL_DIR", tmp_path)
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    now = datetime(2024, 4, 1, 12, 0)
    _seed_decided_game(db_conn, "1", "2024-04-01", atl, nya, home_win=True)
    _seed_prediction(db_conn, "1", "log5-v1", Decimal("0.6"), True, now)
    _seed_prediction(db_conn, "1", "elo-v1", Decimal("0.6"), True, now)
    _seed_prediction(db_conn, "1", "gbm-v1", Decimal("0.6"), True, now)
    db_conn.commit()

    try:
        stack.train(db_conn)
        raise AssertionError("expected ValueError for too few qualifying games")
    except ValueError as exc:
        assert "too few" in str(exc)

    _reset(db_conn)


def test_train_produces_metrics_and_saves_when_it_beats_all_three_baselines(
    db_conn, tmp_path, monkeypatch
):
    monkeypatch.setattr(stack, "MODEL_PATH", tmp_path / "test-stack.json")
    monkeypatch.setattr(stack, "MODEL_DIR", tmp_path)
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    _seed_synthetic_stack_games(db_conn, atl, nya, count=200, start_pk=500000)

    metrics = stack.train(db_conn)

    assert metrics["train_rows"] == 160
    assert metrics["test_rows"] == 40
    for name in ("stack", "log5", "elo", "gbm"):
        assert metrics[name]["log_loss"] > 0
        assert 0 <= metrics[name]["brier"] <= 1
    assert metrics["stack"]["log_loss"] < metrics["log5"]["log_loss"]
    assert metrics["stack"]["log_loss"] < metrics["elo"]["log_loss"]
    assert metrics["stack"]["log_loss"] < metrics["gbm"]["log_loss"]
    assert metrics["saved"] is True
    assert (tmp_path / "test-stack.json").exists()

    _reset(db_conn)


def test_saved_flag_always_matches_whether_the_model_file_was_actually_written(
    db_conn, tmp_path, monkeypatch
):
    # Mirrors gbm.py's own test discipline: never assert a model "must"
    # beat its baselines on some particular draw -- just that "saved"
    # accurately reflects reality, so train() never silently overwrites
    # (or silently fails to report writing) a model.
    monkeypatch.setattr(stack, "MODEL_PATH", tmp_path / "test-stack.json")
    monkeypatch.setattr(stack, "MODEL_DIR", tmp_path)
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    _seed_synthetic_stack_games(db_conn, atl, nya, count=20, start_pk=600000, seed=7)

    metrics = stack.train(db_conn)

    assert (tmp_path / "test-stack.json").exists() == metrics["saved"]

    _reset(db_conn)


def test_predict_writes_predictions_for_undecided_games_with_all_three_base_models(
    db_conn, tmp_path, monkeypatch
):
    monkeypatch.setattr(stack, "MODEL_PATH", tmp_path / "test-stack.json")
    monkeypatch.setattr(stack, "MODEL_DIR", tmp_path)
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    _seed_synthetic_stack_games(db_conn, atl, nya, count=200, start_pk=500000)
    metrics = stack.train(db_conn)
    assert metrics["saved"] is True  # this synthetic pattern is learnable -- must save

    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute(
            "INSERT INTO gold.game_feature (mlb_game_pk, season, game_date, home_win) "
            "VALUES ('900001', 2024, '2024-08-01', NULL)"
        )
    now = datetime(2024, 8, 1, 12, 0)
    _seed_prediction(db_conn, "900001", "log5-v1", Decimal("0.55"), None, now)
    _seed_prediction(db_conn, "900001", "elo-v1", Decimal("0.60"), None, now)
    _seed_prediction(db_conn, "900001", "gbm-v1", Decimal("0.58"), None, now)
    db_conn.commit()

    inserted = stack.predict(db_conn)

    assert inserted == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_win_prob, model_version FROM gold.prediction "
            "WHERE model_version = 'stack-v1'"
        )
        rows = cur.fetchall()
    assert len(rows) == 1
    prob, model_version = rows[0]
    assert model_version == "stack-v1"
    assert Decimal("0") <= prob <= Decimal("1")

    _reset(db_conn)


def test_predict_skips_games_missing_one_base_model(db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(stack, "MODEL_PATH", tmp_path / "test-stack.json")
    monkeypatch.setattr(stack, "MODEL_DIR", tmp_path)
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    _seed_synthetic_stack_games(db_conn, atl, nya, count=200, start_pk=500000)
    stack.train(db_conn)

    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute(
            "INSERT INTO gold.game_feature (mlb_game_pk, season, game_date, home_win) "
            "VALUES ('900002', 2024, '2024-08-01', NULL)"
        )
    now = datetime(2024, 8, 1, 12, 0)
    _seed_prediction(db_conn, "900002", "log5-v1", Decimal("0.55"), None, now)
    _seed_prediction(db_conn, "900002", "elo-v1", Decimal("0.60"), None, now)
    # gbm-v1 missing entirely.
    db_conn.commit()

    inserted = stack.predict(db_conn)

    assert inserted == 0

    _reset(db_conn)


def test_predict_uses_the_latest_base_model_predictions_not_a_stale_one(
    db_conn, tmp_path, monkeypatch
):
    monkeypatch.setattr(stack, "MODEL_PATH", tmp_path / "test-stack.json")
    monkeypatch.setattr(stack, "MODEL_DIR", tmp_path)
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    _seed_synthetic_stack_games(db_conn, atl, nya, count=200, start_pk=500000)
    stack.train(db_conn)

    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute(
            "INSERT INTO gold.game_feature (mlb_game_pk, season, game_date, home_win) "
            "VALUES ('900003', 2024, '2024-08-01', NULL)"
        )
    early = datetime(2024, 8, 1, 6, 0)
    late = datetime(2024, 8, 1, 18, 0)
    # Stale, superseded predictions from earlier the same day.
    _seed_prediction(db_conn, "900003", "log5-v1", Decimal("0.05"), None, early)
    _seed_prediction(db_conn, "900003", "elo-v1", Decimal("0.05"), None, early)
    _seed_prediction(db_conn, "900003", "gbm-v1", Decimal("0.05"), None, early)
    # Latest predictions -- what predict() must actually use.
    _seed_prediction(db_conn, "900003", "log5-v1", Decimal("0.95"), None, late)
    _seed_prediction(db_conn, "900003", "elo-v1", Decimal("0.95"), None, late)
    _seed_prediction(db_conn, "900003", "gbm-v1", Decimal("0.95"), None, late)
    db_conn.commit()

    rows = stack._fetch_predict_rows(db_conn)

    assert len(rows) == 1
    _game_pk, log5_prob, elo_prob, gbm_prob, poly_prob, kalshi_prob = rows[0]
    assert float(log5_prob) == 0.95
    assert float(elo_prob) == 0.95
    assert float(gbm_prob) == 0.95

    _reset(db_conn)


def test_rerunning_predict_before_game_day_preserves_prediction_history(
    db_conn, tmp_path, monkeypatch
):
    # gold.prediction is deliberately history-preserving (migration 0013) --
    # same contract log5.predict()/elo.predict()/gbm.predict() already have
    # (see tests/integration/test_model_log5.py's own version of this test).
    # Re-running predict() for a still-undecided game adds another row, it
    # doesn't overwrite or skip.
    monkeypatch.setattr(stack, "MODEL_PATH", tmp_path / "test-stack.json")
    monkeypatch.setattr(stack, "MODEL_DIR", tmp_path)
    _reset(db_conn)
    teams = _seed_teams(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    _seed_synthetic_stack_games(db_conn, atl, nya, count=200, start_pk=500000)
    stack.train(db_conn)

    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute(
            "INSERT INTO gold.game_feature (mlb_game_pk, season, game_date, home_win) "
            "VALUES ('900004', 2024, '2024-08-01', NULL)"
        )
    now = datetime(2024, 8, 1, 12, 0)
    _seed_prediction(db_conn, "900004", "log5-v1", Decimal("0.55"), None, now)
    _seed_prediction(db_conn, "900004", "elo-v1", Decimal("0.60"), None, now)
    _seed_prediction(db_conn, "900004", "gbm-v1", Decimal("0.58"), None, now)
    db_conn.commit()

    first = stack.predict(db_conn)
    db_conn.commit()
    second = stack.predict(db_conn)
    db_conn.commit()

    assert first == 1
    assert second == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM gold.prediction WHERE model_version = 'stack-v1'")
        (count,) = cur.fetchone()
    assert count == 2

    _reset(db_conn)


def test_predict_returns_zero_when_no_model_saved_yet(db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(stack, "MODEL_PATH", tmp_path / "never-trained.json")
    _reset(db_conn)

    assert stack.predict(db_conn) == 0


def test_health_check_reports_missing_model_file(tmp_path, monkeypatch):
    monkeypatch.setattr(stack, "MODEL_PATH", tmp_path / "never-trained.json")

    check = stack.health_check()[0]

    assert not check.ok
    assert "mlb train" in check.detail


def test_health_check_reports_present_model_file(tmp_path, monkeypatch):
    model_path = tmp_path / "test-stack.json"
    model_path.write_text('{"features": [], "coef": [], "intercept": 0.0}')
    monkeypatch.setattr(stack, "MODEL_PATH", model_path)

    check = stack.health_check()[0]

    assert check.ok
    assert str(model_path) == check.detail
