"""Staged landing (dlt-ingestion-layer 2.0 / 2.0b): policies, one transaction, honest counts.
Real PostgreSQL, no network."""

import dataclasses

import polars as pl
import psycopg
import pytest
from dlt.pipeline.exceptions import PipelineStepFailed

from mlb_baseball import market_store as ms
from mlb_baseball.ingest_layer import land as land_mod
from mlb_baseball.ingest_layer.land import ITEM, Item, Policy, land
from mlb_baseball.ingest_layer.types import arrow_schema

SRC, DS = "spike", "land_t"
TABLE = ms.MarketTable(
    name="raw._land_t",
    reject="raw._land_t_reject",
    columns=(
        ms.Column("id", nullable=False),
        ms.Column("ts", "bigint", nullable=False),
        ms.Column("price", "double precision"),
    ),
    key=("id", "ts"),
)


@pytest.fixture
def conn_factory(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw._land_t (id text NOT NULL, ts bigint NOT NULL,"
            " price double precision,"
            " PRIMARY KEY (id, ts))"
        )
        cur.execute("CREATE TABLE raw._land_t_reject (id text, ts text, price text, reason text)")
    db_conn.commit()
    info = db_conn.info
    yield lambda: psycopg.connect(info.dsn, password=info.password)
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw._land_t, raw._land_t_reject")
        cur.execute("DELETE FROM meta.ingestion_item WHERE source = %s", (SRC,))
    db_conn.commit()


def _frame(item, rows):
    return pl.DataFrame(
        {
            ITEM: [item] * len(rows),
            "id": [r[0] for r in rows],
            "ts": [r[1] for r in rows],
            "price": [r[2] for r in rows],
        },
        schema={ITEM: pl.String, "id": pl.String, "ts": pl.String, "price": pl.String},
    )


def _go(factory, policy, frame, items, **kw):
    return land(factory, TABLE, policy, frame, source=SRC, dataset=DS, items=items, **kw)


def _q(db_conn, query, args=()):
    with db_conn.cursor() as cur:
        cur.execute(query, args)
        out = cur.fetchall()
    db_conn.rollback()
    return out


def test_append_counts_inserted_rows_and_second_run_changes_nothing(db_conn, conn_factory):
    frame = _frame("a", [("x", "1", "0.5"), ("x", "2", "0.6"), ("x", "2", "0.6")])  # dup key
    first = _go(
        conn_factory,
        Policy.APPEND,
        frame,
        [Item("a", source_url="u", artifact_sha256="h", run_id=None)],
    )
    assert first.inserted == {"a": 2}
    second = _go(conn_factory, Policy.APPEND, frame, [Item("a")])
    assert second.inserted == {"a": 0}
    assert _q(db_conn, "SELECT count(*) FROM raw._land_t") == [(2,)]
    assert _q(db_conn, "SELECT rows FROM meta.ingestion_item WHERE source = %s", (SRC,)) == [(0,)]


def test_many_items_one_run_each_get_a_ledger_row_with_provenance(db_conn, conn_factory):
    frame = pl.concat(
        [_frame("a", [("x", "1", "1")]), _frame("b", [("y", "1", "2"), ("y", "2", "3")])]
    )
    items = [
        Item("a", source_url="http://a", artifact_sha256="aa", schema_fingerprint="f1"),
        Item("b"),
    ]
    result = _go(conn_factory, Policy.APPEND, frame, items)
    assert result.inserted == {"a": 1, "b": 2}
    rows = _q(
        db_conn,
        "SELECT item_key, rows, source_url, artifact_sha256, schema_fingerprint "
        "FROM meta.ingestion_item WHERE source = %s ORDER BY 1",
        (SRC,),
    )
    assert rows == [("a", 1, "http://a", "aa", "f1"), ("b", 2, None, None, None)]


def test_empty_is_null_and_bad_rows_go_to_reject_table(db_conn, conn_factory):
    frame = _frame("a", [("x", "1", ""), ("x", "2", "oops"), ("", "3", "1")])
    result = _go(conn_factory, Policy.APPEND, frame, [Item("a")])
    assert result.inserted == {"a": 1} and result.rejected == 2
    assert _q(db_conn, "SELECT id, ts, price FROM raw._land_t") == [("x", 1, None)]
    assert _q(db_conn, "SELECT ts, price, reason FROM raw._land_t_reject ORDER BY ts") == [
        ("2", "oops", "price is not a valid double precision"),
        ("3", "1", "id is empty"),
    ]


def test_text_with_commas_quotes_and_empty_survives_the_csv_copy(db_conn, conn_factory):
    t = dataclasses.replace(TABLE, columns=TABLE.columns + (ms.Column("note"),))
    frame = _frame("a", [("a,b", "1", "1"), ('q"uote', "2", "2"), ("x", "3", "3")]).with_columns(
        note=pl.Series(["has,comma", 'has"quote', ""])
    )
    with conn_factory() as c:
        c.execute("ALTER TABLE raw._land_t ADD COLUMN note text")
    land(conn_factory, t, Policy.APPEND, frame, source=SRC, dataset=DS, items=[Item("a")])
    assert _q(db_conn, "SELECT id, note FROM raw._land_t ORDER BY ts") == [
        ("a,b", "has,comma"),
        ('q"uote', 'has"quote'),
        ("x", None),
    ]


def test_replace_scope_replaces_and_a_zero_row_item_still_deletes(db_conn, conn_factory):
    seed = _frame("g1", [("g1", "1", "1"), ("g1", "2", "2")])
    _go(conn_factory, Policy.REPLACE_SCOPE, seed, [Item("g1", scope={"id": "g1"})])
    again = _frame("g1", [("g1", "5", "5")])
    _go(conn_factory, Policy.REPLACE_SCOPE, again, [Item("g1", scope={"id": "g1"})])
    assert _q(db_conn, "SELECT ts FROM raw._land_t") == [(5,)]
    empty = _frame("g1", [])
    result = _go(conn_factory, Policy.REPLACE_SCOPE, empty, [Item("g1", scope={"id": "g1"})])
    assert result.inserted == {"g1": 0}
    assert _q(db_conn, "SELECT count(*) FROM raw._land_t") == [(0,)]
    assert _q(
        db_conn, "SELECT status, rows FROM meta.ingestion_item WHERE source = %s", (SRC,)
    ) == [("loaded", 0)]


def test_upsert_updates_and_truncate_empties(db_conn, conn_factory):
    _go(conn_factory, Policy.UPSERT, _frame("a", [("x", "1", "1")]), [Item("a")])
    _go(conn_factory, Policy.UPSERT, _frame("a", [("x", "1", "9")]), [Item("a")])
    assert _q(db_conn, "SELECT price FROM raw._land_t") == [(9.0,)]
    _go(conn_factory, Policy.TRUNCATE, _frame("a", [("z", "7", "7")]), [Item("a")])
    assert _q(db_conn, "SELECT id FROM raw._land_t") == [("z",)]


def test_failure_after_rows_rolls_back_rows_and_ledger(db_conn, conn_factory):
    frame = _frame("a", [("x", "1", "1")])
    with pytest.raises(psycopg.errors.NotNullViolation):  # ledger write fails after the rows
        land(conn_factory, TABLE, Policy.APPEND, frame, source=None, dataset=DS, items=[Item("a")])
    assert _q(db_conn, "SELECT count(*) FROM raw._land_t") == [(0,)]
    assert _q(db_conn, "SELECT count(*) FROM meta.ingestion_item WHERE dataset = %s", (DS,)) == [
        (0,)
    ]


def test_failed_dlt_load_never_reaches_the_database_or_the_next_item(
    db_conn, conn_factory, tmp_path, monkeypatch
):
    real = land_mod.pq.read_table
    broken = {"on": True}

    def flaky(path):
        if broken["on"]:
            raise RuntimeError("disk")
        return real(path)

    monkeypatch.setattr(land_mod.pq, "read_table", flaky)
    with pytest.raises(PipelineStepFailed):
        _go(
            conn_factory,
            Policy.APPEND,
            _frame("a", [("A", "1", "1")]),
            [Item("a")],
            state_dir=tmp_path,
        )
    broken["on"] = False
    _go(
        conn_factory, Policy.APPEND, _frame("b", [("B", "1", "1")]), [Item("b")], state_dir=tmp_path
    )
    assert _q(db_conn, "SELECT id FROM raw._land_t") == [("B",)]
    assert _q(db_conn, "SELECT item_key FROM meta.ingestion_item WHERE source = %s", (SRC,)) == [
        ("b",)
    ]


def test_new_source_field_is_added_as_text_and_reported(db_conn, conn_factory):
    frame = _frame("a", [("x", "1", "1")]).with_columns(venue=pl.lit("park"))
    result = _go(conn_factory, Policy.APPEND, frame, [Item("a")])
    assert result.new_columns == ["venue"]
    assert _q(db_conn, "SELECT venue FROM raw._land_t") == [("park",)]


def test_declared_arrow_schema_matches_the_real_market_tables(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT meta.create_market_tables('_t')")
        for spec, rel in (
            (ms.POLYMARKET_PRICE, "polymarket_price_t"),
            (ms.KALSHI_CANDLE, "kalshi_candle_t"),
        ):
            cur.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema='raw' AND table_name=%s",
                (rel,),
            )
            db = dict(cur.fetchall())
            for field in arrow_schema(spec):
                assert field.name in db, (rel, field.name)
        cur.execute("DROP TABLE raw.polymarket_price_t, raw.kalshi_candle_t")
    db_conn.commit()
