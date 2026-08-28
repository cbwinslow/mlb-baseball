import pytest

from mlb_baseball.model import evaluation


def _ensure_schedule_shape(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        (exists,) = cur.fetchone()
        if not exists:
            cur.execute(
                "CREATE TABLE raw.mlb_schedule (game_id text, game_datetime text, _season text, "
                "game_date text, game_num text, home_id text, away_id text, game_type text, "
                "status text, venue_id text)"
            )
        else:
            cur.execute("ALTER TABLE raw.mlb_schedule ADD COLUMN IF NOT EXISTS game_datetime text")
            cur.execute("ALTER TABLE raw.mlb_schedule ADD COLUMN IF NOT EXISTS _season text")
            cur.execute("ALTER TABLE raw.mlb_schedule ADD COLUMN IF NOT EXISTS game_date text")
            cur.execute("ALTER TABLE raw.mlb_schedule ADD COLUMN IF NOT EXISTS game_num text")
            cur.execute("ALTER TABLE raw.mlb_schedule ADD COLUMN IF NOT EXISTS home_id text")
            cur.execute("ALTER TABLE raw.mlb_schedule ADD COLUMN IF NOT EXISTS away_id text")
            cur.execute("ALTER TABLE raw.mlb_schedule ADD COLUMN IF NOT EXISTS game_type text")
            cur.execute("ALTER TABLE raw.mlb_schedule ADD COLUMN IF NOT EXISTS status text")
            cur.execute("ALTER TABLE raw.mlb_schedule ADD COLUMN IF NOT EXISTS venue_id text")
    db_conn.commit()


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM meta.model_evaluation")
        # meta.game_instance was missing here even though this file itself
        # writes to it (test_evaluate_retains_retrosheet_history_after_
        # feature_rows_are_rebuilt): _selected_predictions()'s instance_rows
        # CTE prefers a real meta.game_instance row over gold.game_feature
        # for the same game_instance_key -- a leftover row from an earlier
        # test in this repo's shared, session-scoped test database (see
        # tests/conftest.py's _test_database fixture) with a stale
        # season/game_date silently shadowed this test's own fresh
        # gold.game_feature insert, producing a real, reproducible
        # coverage={} bug only visible once the full suite runs together.
        cur.execute("DELETE FROM meta.game_instance")
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
    db_conn.commit()


@pytest.fixture(autouse=True)
def _clean(db_conn):
    _reset(db_conn)
    yield
    _reset(db_conn)


def test_evaluate_treats_schedule_history_as_one_mlb_game(db_conn):
    _ensure_schedule_shape(db_conn)
    key = "mlb:999"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, game_datetime, _season, game_date, game_num, home_id, away_id) VALUES "
            "('999', '2026-05-01T20:00:00Z', '2026', '2026-05-01', '1', '10', '20'), "
            "('999', '2026-05-02T20:00:00Z', '2026', '2026-05-02', '1', '30', '40')"
        )
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(mlb_game_pk, game_instance_key, season, game_date) VALUES "
            "('999', %s, 2026, '2026-05-01')",
            (key,),
        )
        cur.execute(
            "INSERT INTO gold.prediction "
            "(mlb_game_pk, game_instance_key, model_version, generated_at, home_win_prob, "
            "actual_home_win) VALUES "
            "('999', %s, 'a', '2026-05-01T19:00:00Z', 0.70, true)",
            (key,),
        )
    db_conn.commit()

    report = evaluation.evaluate(db_conn, ["a"], season=2026, bootstrap_samples=5)

    assert report["coverage"] == {"a": 1}
    assert report["common_games"] == 1


def test_evaluate_uses_one_pregame_snapshot_and_exact_common_sample(db_conn):
    _ensure_schedule_shape(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, game_datetime, _season, game_date, game_num, home_id, away_id) VALUES "
            "('1001', '2026-06-01T19:00:00Z', '2026', '2026-06-01', '1', '1', '2'), "
            "('1002', '2026-06-02T19:00:00Z', '2026', '2026-06-02', '1', '3', '4')"
        )
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(mlb_game_pk, game_instance_key, season, game_date) VALUES "
            "('1001', 'mlb:1001', 2026, '2026-06-01'), "
            "('1002', 'mlb:1002', 2026, '2026-06-02')"
        )
        cur.execute(
            "INSERT INTO gold.prediction ("
            "mlb_game_pk, game_instance_key, model_version, generated_at, "
            "home_win_prob, actual_home_win) VALUES "
            # Game 1001: multiple snapshots for model 'm1' and 'm2'
            "('1001', 'mlb:1001', 'm1', '2026-06-01T12:00:00Z', 0.55, true), "
            "('1001', 'mlb:1001', 'm1', '2026-06-01T18:30:00Z', 0.65, true), "
            # Post-game leak (must be ignored)
            "('1001', 'mlb:1001', 'm1', '2026-06-01T20:00:00Z', 0.99, true), "
            "('1001', 'mlb:1001', 'm2', '2026-06-01T18:00:00Z', 0.60, true), "
            # Game 1002: only covered by model 'm1'
            "('1002', 'mlb:1002', 'm1', '2026-06-02T18:00:00Z', 0.40, false)"
        )
    db_conn.commit()

    report = evaluation.evaluate(
        db_conn, ["m1", "m2"], season=2026, cutoff="close", bootstrap_samples=10
    )

    assert report["coverage"] == {"m1": 2, "m2": 1}
    assert report["common_games"] == 1
    assert report["models"]["m1"]["games"] == 1
    assert report["models"]["m2"]["games"] == 1
    assert report["models"]["m1"]["brier"] == pytest.approx(0.1225, abs=1e-4)
    assert report["models"]["m2"]["brier"] == pytest.approx(0.1600, abs=1e-4)


def test_evaluate_retains_retrosheet_history_after_feature_rows_are_rebuilt(db_conn):
    key = "retro:HIST202604010"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.game_instance "
            "(game_instance_key, identity_kind, season, game_date, retro_game_id) "
            "VALUES (%s, 'retrosheet', 2026, '2026-04-01', 'HIST202604010') "
            "ON CONFLICT (game_instance_key) DO UPDATE SET last_seen_at = now()",
            (key,),
        )
        cur.execute(
            "INSERT INTO gold.prediction "
            "(mlb_game_pk, game_instance_key, model_version, generated_at, home_win_prob, "
            "actual_home_win) VALUES ('legacy', %s, 'a', '2026-04-01T20:00:00Z', 0.60, true)",
            (key,),
        )
    db_conn.commit()

    report = evaluation.evaluate(db_conn, ["a"], season=2026, bootstrap_samples=5)

    assert report["coverage"] == {"a": 1}
    assert report["common_games"] == 1
    _reset(db_conn)
    _ensure_schedule_shape(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, game_datetime, _season, game_date, game_num, home_id, away_id) VALUES "
            "('1', '2026-04-01T20:00:00Z', '2026', '2026-04-01', '1', '1', '2'), "
            "('2', '2026-04-02T20:00:00Z', '2026', '2026-04-02', '1', '3', '4')"
        )
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(mlb_game_pk, game_instance_key, season, game_date) VALUES "
            "('1', 'mlb:1', 2026, '2026-04-01'), "
            "('2', 'mlb:2', 2026, '2026-04-02')"
        )
        cur.execute(
            "INSERT INTO gold.prediction "
            "(mlb_game_pk, game_instance_key, model_version, generated_at, home_win_prob, "
            "actual_home_win) VALUES "
            "('1', 'mlb:1', 'a', '2026-04-01T10:00:00Z', 0.40, true), "
            "('1', 'mlb:1', 'a', '2026-04-01T19:00:00Z', 0.80, true), "
            "('1', 'mlb:1', 'a', '2026-04-01T21:00:00Z', 0.01, true), "
            "('1', 'mlb:1', 'b', '2026-04-01T11:00:00Z', 0.70, true), "
            "('1', 'mlb:1', 'b', '2026-04-01T19:00:00Z', 0.75, true), "
            "('2', 'mlb:2', 'a', '2026-04-02T19:00:00Z', 0.20, false)"
        )
    db_conn.commit()

    report = evaluation.evaluate(
        db_conn, ["a", "b"], season=2026, cutoff="close", bootstrap_samples=20
    )

    assert report["coverage"] == {"a": 2, "b": 1}
    assert report["common_games"] == 1
    assert report["models"]["a"]["games"] == 1
    assert report["models"]["a"]["brier"] == pytest.approx(0.04)

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT e.common_games, r.run_type, r.status "
            "FROM meta.model_evaluation e JOIN meta.model_run r ON r.run_id = e.run_id "
            "WHERE e.evaluation_id = %s",
            (report["evaluation_id"],),
        )
        persisted = cur.fetchone()
    assert persisted == (1, "evaluate", "success")
