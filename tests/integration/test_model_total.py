"""Regression coverage for mlb_baseball.model.total -- run-total (over/
under) regression, a genuinely different target from log5/elo/gbm (win/loss
classification). See mlb_baseball/model/total.py's own module docstring for
the full reasoning (regression vs. a specific betting line, feature
selection, the park-trailing-average baseline).

core.game is seeded directly for the trailing-league-average feeder seasons
and the labeled train/validation games (real total-runs labels the same
shape core.game actually holds); gold.game_feature is seeded directly for
the feature columns train()/predict() actually read -- same shortcut
test_model_gbm.py/test_model_log5.py already take, since neither function
needs the full features.build()/conform.run() pipeline to exercise its own
logic.
"""

from decimal import Decimal

from mlb_baseball.model import total


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.total_prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
    db_conn.commit()


def _insert_game(db_conn, retro_id, season, game_date, home_score, away_score, game_pk=None):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_score, away_score, game_type, game_pk) "
            "VALUES (%s, %s, %s, %s, %s, 'regular', %s) RETURNING id",
            (retro_id, season, game_date, home_score, away_score, game_pk),
        )
        (game_id,) = cur.fetchone()
    return game_id


def _insert_feature(
    db_conn,
    game_id,
    mlb_game_pk,
    season,
    game_date,
    park_factor,
    home_win,
    home_woba=None,
    away_woba=None,
):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(game_id, mlb_game_pk, game_instance_key, season, game_date, park_factor, "
            "home_win, home_woba, away_woba) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (game_id, mlb_game_pk, f"test:{mlb_game_pk}", season, game_date, park_factor,
             home_win, home_woba, away_woba),
        )


def _seed_learnable_seasons(db_conn, rng_seasons, start_pk):
    """Seeds learnable seasons along TWO independent axes -- park_factor
    (80/120) and team wOBA (0.300/0.340, an OPTIONAL_COLUMNS feature) --
    each shifting total_runs by its own fixed amount, plus small noise.
    park_factor alone is deliberately NOT enough to predict total_runs
    exactly (unlike an earlier version of this fixture): the naive
    baseline itself is *built from* park_factor (see total.py's own
    baseline_total formula), so a park_factor-only synthetic pattern
    would make the baseline already near-optimal and the model unlikely to
    reliably beat it -- confirmed the hard way (a real test failure, not
    a hypothetical): 3 tests failed here because train() correctly
    declined to save a model that didn't actually beat that baseline. The
    wOBA axis gives a real, distinct model-only feature to learn that the
    park-only baseline structurally can't see. Returns the next free pk
    counter."""
    import random

    rng = random.Random(42)
    pk = start_pk
    for season in rng_seasons:
        for i in range(60):
            high_park = i % 2 == 0
            high_offense = (i // 2) % 2 == 0
            park_factor = 120 if high_park else 80
            woba = 0.340 if high_offense else 0.300
            base_total = (11 if high_park else 7) + (2 if high_offense else -2)
            total_runs = max(0, base_total + rng.randint(-1, 1))
            home_score = total_runs // 2
            away_score = total_runs - home_score
            game_id = _insert_game(
                db_conn,
                f"RETRO{season}_{i}",
                season,
                f"{season}-04-{(i % 27) + 1:02d}",
                home_score,
                away_score,
                game_pk=str(pk),
            )
            _insert_feature(
                db_conn, game_id, str(pk), season, f"{season}-04-{(i % 27) + 1:02d}",
                park_factor, home_win=(home_score > away_score),
                home_woba=woba, away_woba=woba,
            )
            pk += 1
    db_conn.commit()
    return pk


def test_train_produces_metrics_and_saves_when_it_beats_baseline(db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(total, "MODEL_PATH", tmp_path / "test-total.json")
    monkeypatch.setattr(total, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(total, "TRAILING_SEASONS", 2)
    monkeypatch.setattr(total, "TRAIN_SEASON_CUTOFF", 2021)
    monkeypatch.setattr(total, "VALIDATION_SEASONS", (2022,))
    _reset(db_conn)
    # 2019/2020 feed the trailing league average entering 2021; 2020/2021
    # feed the trailing average entering 2022 -- every season used here
    # needs real core.game rows, not just the two being trained/validated on.
    _seed_learnable_seasons(db_conn, [2019, 2020, 2021, 2022], start_pk=500000)

    metrics = total.train(db_conn)

    # Seasons <= 2021 that have decided games are {2019, 2020, 2021}, but
    # 2019 has no trailing league history 2 seasons back (nothing before
    # 2019 was seeded at all) -- the inner join to league_trailing excludes
    # it entirely (same "no baseline, no row" precedent the module
    # docstring documents), leaving only 2020+2021 = 120 rows.
    assert metrics["train_rows"] == 120
    assert metrics["validation_rows"] == 60  # only season 2022
    for side in ("model", "baseline"):
        assert metrics[side]["rmse"] > 0
        assert metrics[side]["mae"] > 0
    # Whether it happens to beat the baseline on this particular synthetic
    # draw isn't the point of this test (same precedent as gbm's own) --
    # but "saved" must accurately reflect whether the file was written.
    assert (tmp_path / "test-total.json").exists() == metrics["saved"]

    _reset(db_conn)


def test_predict_writes_baseline_matching_hand_computed_trailing_average(
    db_conn, tmp_path, monkeypatch
):
    # Hand-computed baseline: season 2019 totals [10, 12] (avg 11, 2 games),
    # season 2020 totals [8, 8] (avg 8, 2 games) -- games-weighted trailing
    # average entering 2021 (TRAILING_SEASONS=2, window [2019, 2020]) is
    # (10+12+8+8)/4 = 9.5. An upcoming 2021 game at park_factor=110 should
    # get baseline_total = 9.5 * 110/100 = 10.45 exactly.
    monkeypatch.setattr(total, "MODEL_PATH", tmp_path / "test-total.json")
    monkeypatch.setattr(total, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(total, "TRAILING_SEASONS", 2)
    monkeypatch.setattr(total, "TRAIN_SEASON_CUTOFF", 2021)
    monkeypatch.setattr(total, "VALIDATION_SEASONS", (2022,))
    _reset(db_conn)
    _seed_learnable_seasons(db_conn, [2019, 2020, 2021, 2022], start_pk=600000)
    total.train(db_conn)
    # This synthetic pattern is learnable -- must save.
    assert (tmp_path / "test-total.json").exists()

    _reset_predictions_only(db_conn)
    # Only core.game rows matter for the trailing-league-average baseline --
    # it's computed straight from core.game (season_totals CTE), independent
    # of gold.game_feature entirely, so no game_feature rows are seeded for
    # these four.
    _insert_game(db_conn, "RETRO2019_A", 2019, "2019-04-01", 10, 0, game_pk="700001")
    _insert_game(db_conn, "RETRO2019_B", 2019, "2019-04-02", 6, 6, game_pk="700002")
    _insert_game(db_conn, "RETRO2020_A", 2020, "2020-04-01", 4, 4, game_pk="700003")
    _insert_game(db_conn, "RETRO2020_B", 2020, "2020-04-02", 3, 5, game_pk="700004")
    # The upcoming game itself -- no core.game row at all (matches
    # production shape: an upcoming game only ever exists in
    # gold.game_feature/raw.mlb_schedule until it's actually played).
    _insert_feature(
        db_conn, None, "999999", 2021, "2021-04-01", park_factor=110, home_win=None
    )
    db_conn.commit()

    inserted = total.predict(db_conn)

    assert inserted == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT model_version, predicted_total, baseline_total, actual_total "
            "FROM gold.total_prediction WHERE mlb_game_pk = '999999'"
        )
        model_version, predicted_total, baseline_total, actual_total = cur.fetchone()
    assert model_version == "total-v1"
    assert baseline_total == Decimal("10.45")
    assert predicted_total is not None
    assert actual_total is None

    _reset(db_conn)


def _reset_predictions_only(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.total_prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
    db_conn.commit()


def test_predict_returns_zero_when_no_model_saved_yet(db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(total, "MODEL_PATH", tmp_path / "never-trained.json")
    _reset(db_conn)

    assert total.predict(db_conn) == 0


def test_predict_excludes_rows_missing_required_park_factor(db_conn, tmp_path, monkeypatch):
    monkeypatch.setattr(total, "MODEL_PATH", tmp_path / "test-total.json")
    monkeypatch.setattr(total, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(total, "TRAILING_SEASONS", 2)
    monkeypatch.setattr(total, "TRAIN_SEASON_CUTOFF", 2021)
    monkeypatch.setattr(total, "VALIDATION_SEASONS", (2022,))
    _reset(db_conn)
    _seed_learnable_seasons(db_conn, [2019, 2020, 2021, 2022], start_pk=800000)
    total.train(db_conn)
    assert (tmp_path / "test-total.json").exists()

    _reset_predictions_only(db_conn)
    # park_factor NULL (REQUIRED_COLUMNS) -- must be excluded, not crash
    # trying to convert it, and not silently fall back to some default.
    _insert_feature(db_conn, None, "888888", 2021, "2021-04-01", park_factor=None, home_win=None)
    db_conn.commit()

    inserted = total.predict(db_conn)

    assert inserted == 0
    _reset(db_conn)


def test_rerunning_predict_before_game_day_preserves_prediction_history(
    db_conn, tmp_path, monkeypatch
):
    # gold.total_prediction is deliberately history-preserving, same
    # precedent as gold.prediction (migration 0014, mirrored by
    # test_model_log5.py's own equivalent test) -- re-running predict() for
    # the same still-undecided game before it's played should add another
    # row, not overwrite/skip the first one.
    monkeypatch.setattr(total, "MODEL_PATH", tmp_path / "test-total.json")
    monkeypatch.setattr(total, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(total, "TRAILING_SEASONS", 2)
    monkeypatch.setattr(total, "TRAIN_SEASON_CUTOFF", 2021)
    monkeypatch.setattr(total, "VALIDATION_SEASONS", (2022,))
    _reset(db_conn)
    _seed_learnable_seasons(db_conn, [2019, 2020, 2021, 2022], start_pk=900000)
    total.train(db_conn)
    assert (tmp_path / "test-total.json").exists()

    _reset_predictions_only(db_conn)
    # predict()'s own baseline needs real trailing-season core.game history
    # to resolve league_trailing for season 2021 (TRAILING_SEASONS=2 ->
    # window [2019, 2020]) -- _reset_predictions_only wiped every core.game
    # row, so without this the row below would be silently excluded by
    # predict()'s own inner join (same "no baseline, no row" precedent as
    # the hand-computed-baseline test above), not a bug in predict() itself.
    _insert_game(db_conn, "RETRO2019_FEED", 2019, "2019-04-01", 5, 5, game_pk="900500")
    _insert_game(db_conn, "RETRO2020_FEED", 2020, "2020-04-01", 4, 4, game_pk="900501")
    _insert_feature(db_conn, None, "999003", 2021, "2021-04-01", park_factor=100, home_win=None)
    db_conn.commit()

    first = total.predict(db_conn)
    db_conn.commit()
    second = total.predict(db_conn)
    db_conn.commit()

    assert first == 1
    assert second == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM gold.total_prediction")
        (count,) = cur.fetchone()
    assert count == 2

    _reset(db_conn)


def test_backfill_outcomes_fills_in_actual_total_once_game_is_final(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gold.total_prediction "
            "(mlb_game_pk, model_version, predicted_total, baseline_total) "
            "VALUES ('999004', 'total-v1', 9.1, 8.7)"
        )
    db_conn.commit()
    _insert_game(db_conn, "G_FINAL", 2024, "2024-04-01", 5, 3, game_pk="999004")
    db_conn.commit()

    updated = total.backfill_outcomes(db_conn)

    assert updated == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT actual_total FROM gold.total_prediction WHERE mlb_game_pk = '999004'"
        )
        (actual_total,) = cur.fetchone()
    assert actual_total == 8  # 5 + 3, hand-computed

    _reset(db_conn)


def test_backfill_outcomes_leaves_undecided_games_alone(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gold.total_prediction "
            "(mlb_game_pk, model_version, predicted_total, baseline_total) "
            "VALUES ('999005', 'total-v1', 9.1, 8.7)"
        )
    db_conn.commit()

    updated = total.backfill_outcomes(db_conn)

    assert updated == 0
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT actual_total FROM gold.total_prediction WHERE mlb_game_pk = '999005'"
        )
        (actual_total,) = cur.fetchone()
    assert actual_total is None

    _reset(db_conn)


def test_health_check_reports_missing_model_file(tmp_path, monkeypatch):
    monkeypatch.setattr(total, "MODEL_PATH", tmp_path / "never-trained.json")

    checks = {c.name: c for c in total.health_check()}

    assert f"{total.MODEL_VERSION} model file" in checks
    assert not checks[f"{total.MODEL_VERSION} model file"].ok
    assert "mlb train" in checks[f"{total.MODEL_VERSION} model file"].detail
