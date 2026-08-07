import pytest

from mlb_baseball.model import evaluation


def _ensure_schedule_shape(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        (exists,) = cur.fetchone()
        if not exists:
            cur.execute("CREATE TABLE raw.mlb_schedule (game_id text, game_datetime text)")
        else:
            cur.execute("ALTER TABLE raw.mlb_schedule ADD COLUMN IF NOT EXISTS game_datetime text")
    db_conn.commit()


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        (exists,) = cur.fetchone()
        if exists:
            cur.execute("DELETE FROM raw.mlb_schedule")
    db_conn.commit()


def test_evaluate_uses_one_pregame_snapshot_and_exact_common_sample(db_conn):
    _reset(db_conn)
    _ensure_schedule_shape(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.mlb_schedule (game_id, game_datetime) VALUES "
            "('1', '2026-04-01T20:00:00Z'), ('2', '2026-04-02T20:00:00Z')"
        )
        cur.execute(
            "INSERT INTO gold.game_feature (mlb_game_pk, season, game_date) VALUES "
            "('1', 2026, '2026-04-01'), ('2', 2026, '2026-04-02')"
        )
        cur.execute(
            "INSERT INTO gold.prediction "
            "(mlb_game_pk, model_version, generated_at, home_win_prob, actual_home_win) VALUES "
            # Both models have several snapshots for game 1. Close must
            # select 19:00 and ignore both the older row and postgame leak.
            "('1', 'a', '2026-04-01T10:00:00Z', 0.40, true), "
            "('1', 'a', '2026-04-01T19:00:00Z', 0.80, true), "
            "('1', 'a', '2026-04-01T21:00:00Z', 0.01, true), "
            "('1', 'b', '2026-04-01T11:00:00Z', 0.70, true), "
            "('1', 'b', '2026-04-01T19:00:00Z', 0.75, true), "
            # Only model a covers game 2, so matched comparison excludes it.
            "('2', 'a', '2026-04-02T19:00:00Z', 0.20, false)"
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

    _reset(db_conn)
