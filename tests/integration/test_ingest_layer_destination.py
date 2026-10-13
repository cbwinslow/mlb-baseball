"""Spike (dlt-ingestion-layer 1.2): a dlt custom destination lands a ledger item's rows and
its meta.ingestion_item row in one transaction. Real PostgreSQL, no network."""

import dlt
import psycopg
import pytest
from dlt.pipeline.exceptions import PipelineStepFailed

from mlb_baseball.ingest_layer.destination import item_destination

TARGET = "raw._spike_dlt"
SRC, DS, KEY = "spike", "spike_price", "token-1"


@pytest.fixture
def target(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            f"CREATE TABLE {TARGET} (id text, ts bigint, price double precision, "
            "PRIMARY KEY (id, ts))"
        )
    db_conn.commit()
    yield
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {TARGET}")
        cur.execute("DELETE FROM meta.ingestion_item WHERE source = %s", (SRC,))
    db_conn.commit()


def _run(db_conn, tmp_path, rows, item_key=KEY):
    info = db_conn.info
    dest = item_destination(
        lambda: psycopg.connect(info.dsn, password=info.password),
        target=TARGET,
        key=("id", "ts"),
        source=SRC,
        dataset=DS,
        item_key=item_key,
    )
    pipe = dlt.pipeline("spike", destination=dest, pipelines_dir=str(tmp_path), dataset_name="x")
    try:
        pipe.run(rows, table_name="spike_price", loader_file_format="parquet")
    finally:
        pipe.abort_packages()


def _state(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {TARGET}")
        n = cur.fetchone()[0]
        cur.execute("SELECT status, rows FROM meta.ingestion_item WHERE source = %s", (SRC,))
        ledger = cur.fetchall()
    db_conn.rollback()
    return n, ledger


ROWS = [{"id": "a", "ts": i, "price": i / 10} for i in range(5)]


def test_rows_and_ledger_land_together_and_second_run_changes_nothing(db_conn, target, tmp_path):
    _run(db_conn, tmp_path / "1", ROWS)
    assert _state(db_conn) == (5, [("loaded", 5)])
    _run(db_conn, tmp_path / "2", ROWS)
    assert _state(db_conn) == (5, [("loaded", 5)])


def test_mid_item_failure_leaves_neither_rows_nor_ledger(db_conn, target, tmp_path):
    bad = ROWS + [{"id": "a", "ts": 99, "price": "not-a-number"}]  # fails after 5 inserts
    with pytest.raises(PipelineStepFailed):
        _run(db_conn, tmp_path / "1", bad)
    assert _state(db_conn) == (0, [])


def test_ledger_failure_after_rows_inserted_rolls_the_rows_back(db_conn, target, tmp_path):
    # rows insert fine, then the ledger write violates NOT NULL: the rows must not survive
    with pytest.raises(PipelineStepFailed):
        _run(db_conn, tmp_path / "1", ROWS, item_key=None)
    assert _state(db_conn) == (0, [])
