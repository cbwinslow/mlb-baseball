import uuid
from datetime import date

import psycopg
import pytest

from mlb_baseball.ingest import track_run
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
    #
    # Deliberately does NOT commit after start_run() here (PR review,
    # CodeAnt caught this as a real gap: every real caller -- elo.py,
    # log5.py, gbm.py, evaluation.py -- calls start_run() then goes
    # straight into its own real work with no commit in between, so a
    # test that manually committed here wouldn't actually exercise the
    # real failure shape). start_run() now commits its own INSERT
    # internally for exactly this reason -- proven by this test still
    # finding the run row after the rollback below.
    _reset(db_conn)
    run_id = provenance.start_run(db_conn, run_type="evaluate")

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


def test_finish_run_failure_record_survives_the_real_track_run_nesting(db_conn):
    # Regression (PR #59 review, Kilo -- a real, confirmed bug the test
    # above didn't catch): every real caller of start_run()/finish_run()
    # (log5.py/elo.py/gbm.py's predict()/train()) is itself only ever
    # invoked from model/__init__.py's run(), inside ingest.py's own
    # track_run() context manager. track_run's own except-block does a
    # *second* conn.rollback() when the re-raised exception reaches it --
    # without finish_run() committing its own UPDATE first, that second
    # rollback would silently wipe out the failure record this whole fix
    # chain exists to guarantee. Reproduces the real nesting shape
    # directly, not just finish_run() in isolation.
    _reset(db_conn)
    source = f"test_provenance_nesting_{uuid.uuid4().hex}"

    with pytest.raises(RuntimeError, match="boom"):
        with track_run(db_conn, source, "bootstrap"):
            run_id = provenance.start_run(db_conn, run_type="predict")
            try:
                raise RuntimeError("boom")
            except RuntimeError as error:
                provenance.finish_run(db_conn, run_id, error=error)
                raise

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT status, error FROM meta.model_run WHERE run_id = %s",
            (run_id,),
        )
        status, error = cur.fetchone()
    assert status == "failed"
    assert "boom" in error

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
