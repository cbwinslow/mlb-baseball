from datetime import date

import psycopg
import pytest

from mlb_baseball.model import provenance


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("UPDATE gold.prediction SET model_id = NULL, model_run_id = NULL")
        cur.execute("DELETE FROM meta.model_evaluation")
        cur.execute("DELETE FROM meta.model_run")
        cur.execute("DELETE FROM meta.model")
    db_conn.commit()


def test_register_model_promotes_one_immutable_champion(db_conn, tmp_path):
    _reset(db_conn)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text("first")
    second.write_text("second")

    first_id = provenance.register_model(
        db_conn,
        name="gbm",
        target="home_win",
        model_version="gbm-v2",
        feature_set_version="game-feature-v1",
        status="champion",
        artifact_path=first,
    )
    second_id = provenance.register_model(
        db_conn,
        name="gbm",
        target="home_win",
        model_version="gbm-v2",
        feature_set_version="game-feature-v1",
        status="champion",
        artifact_path=second,
    )
    run_id = provenance.start_run(db_conn, run_type="predict", model_id=second_id)
    provenance.finish_run(db_conn, run_id)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT model_id, status FROM meta.model ORDER BY model_id")
        statuses = dict(cur.fetchall())
        cur.execute("SELECT status, finished_at IS NOT NULL FROM meta.model_run")
        run = cur.fetchone()
    assert first_id != second_id
    assert statuses[first_id] == "retired"
    assert statuses[second_id] == "champion"
    assert run == ("success", True)

    _reset(db_conn)


def test_registering_an_existing_champion_as_candidate_does_not_demote_it(db_conn, tmp_path):
    _reset(db_conn)
    artifact = tmp_path / "model.json"
    artifact.write_text("same artifact")

    model_id = provenance.register_model(
        db_conn,
        name="gbm",
        target="home_win",
        model_version="gbm-v1",
        feature_set_version="game-feature-v1",
        status="champion",
        artifact_path=artifact,
    )
    repeated_id = provenance.register_model(
        db_conn,
        name="gbm",
        target="home_win",
        model_version="gbm-v1",
        feature_set_version="game-feature-v1",
        status="candidate",
        artifact_path=artifact,
    )
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT status FROM meta.model WHERE model_id = %s", (model_id,))
        status = cur.fetchone()
    assert repeated_id == model_id
    assert status == ("champion",)

    _reset(db_conn)


def test_finish_run_logs_failure_after_an_aborted_transaction(db_conn):
    # Regression: finish_run used to try logging the failure without
    # rolling back the aborted transaction first (the caller's own failed
    # operation typically leaves db_conn in InFailedSqlTransaction state),
    # which raised a second, more confusing error that masked the real one
    # and left no failure record at all -- same bug class, same fix, as
    # ingest.py's track_run (see its own
    # test_failure_path_logs_error_and_leaves_connection_usable, the
    # reference example for this pattern).
    _reset(db_conn)
    run_id = provenance.start_run(db_conn, run_type="evaluate")
    db_conn.commit()

    with db_conn.cursor() as cur, pytest.raises(psycopg.errors.UndefinedTable):
        cur.execute("SELECT * FROM raw.this_table_does_not_exist")
    assert db_conn.info.transaction_status == psycopg.pq.TransactionStatus.INERROR

    provenance.finish_run(db_conn, run_id, error=RuntimeError("boom"))
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT status, error, finished_at IS NOT NULL FROM meta.model_run WHERE run_id = %s",
            (run_id,),
        )
        status, error, has_finished_at = cur.fetchone()
    assert status == "failed"
    assert "boom" in error
    assert has_finished_at

    with db_conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)

    _reset(db_conn)


def test_feature_snapshot_records_the_actual_feature_build_state(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute(
            "INSERT INTO gold.game_feature (game_instance_key, season, game_date) "
            "VALUES ('test:feature-snapshot', 2025, '2025-10-01')"
        )
    db_conn.commit()

    data_cutoff, snapshot_id = provenance.feature_snapshot(conn=db_conn)

    assert data_cutoff is not None
    assert "rows=1" in snapshot_id
    assert "latest_game_date=2025-10-01" in snapshot_id

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT row_count, latest_game_date, identity_json->>'selection' "
            "FROM meta.feature_snapshot WHERE feature_snapshot_id = %s",
            (snapshot_id,),
        )
        persisted = cur.fetchone()
    assert persisted == (1, date(2025, 10, 1), "TRUE")

    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.game_feature")
    db_conn.commit()
