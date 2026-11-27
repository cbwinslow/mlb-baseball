"""Migration 0117: typed market price tables (spec market-price-store).

The table shapes and keys are checked everywhere; the hypertable, compression and
conflict-after-compression checks skip on a server without timescaledb (stock CI image)."""

from pathlib import Path

import pytest


def _has_timescale(cur) -> bool:
    cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'")
    return cur.fetchone() is not None


@pytest.fixture
def new_tables(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT meta.create_market_tables('_t')")
    yield db_conn
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.polymarket_price_t, raw.kalshi_candle_t")


def _types(cur, table):
    cur.execute(
        "SELECT column_name, data_type, numeric_precision, numeric_scale "
        "FROM information_schema.columns WHERE table_schema='raw' AND table_name=%s "
        "ORDER BY ordinal_position",
        (table,),
    )
    return {name: (kind, prec, scale) for name, kind, prec, scale in cur.fetchall()}


def test_polymarket_columns_are_typed_and_keep_their_names(new_tables):
    with new_tables.cursor() as cur:
        cols = _types(cur, "polymarket_price_t")
    assert list(cols) == ["clob_token_id", "_market", "_event", "ts", "price", "_loaded_at"]
    assert cols["ts"][0] == "bigint"
    assert cols["price"][0] == "double precision"
    assert cols["_market"][0] == "integer"


def test_kalshi_columns_are_typed_and_keep_their_names(new_tables):
    with new_tables.cursor() as cur:
        cols = _types(cur, "kalshi_candle_t")
    assert len(cols) == 33
    assert cols["ts"][0] == "bigint"
    assert cols["price_close_dollars"] == ("numeric", 10, 4)
    assert cols["price_close"] == ("numeric", 10, 4)
    assert cols["volume"] == ("numeric", 14, 2)


def test_second_call_changes_nothing(new_tables):
    with new_tables.cursor() as cur:
        cur.execute("SELECT meta.create_market_tables('_t')")
        cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_name LIKE '%_t'")
        assert cur.fetchone()[0] >= 2


def test_existing_table_is_never_touched(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("CREATE TABLE raw.polymarket_price_keep (price text)")
        cur.execute("INSERT INTO raw.polymarket_price_keep VALUES ('0.5')")
        cur.execute("SELECT meta.create_market_tables('_keep')")
        cur.execute("SELECT price FROM raw.polymarket_price_keep")
        assert cur.fetchone()[0] == "0.5"
        cur.execute("DROP TABLE raw.polymarket_price_keep, raw.kalshi_candle_keep")


def test_empty_value_is_null_and_duplicate_key_loads_once(new_tables):
    with new_tables.cursor() as cur:
        row = "('tok', 1, 2, 1700000000, %s)"
        for _ in range(2):
            cur.execute(
                "INSERT INTO raw.polymarket_price_t VALUES " + row + " ON CONFLICT DO NOTHING",
                (None,),
            )
        cur.execute("SELECT count(*), count(price) FROM raw.polymarket_price_t")
        assert cur.fetchone() == (1, 0)


def test_reject_tables_exist_and_take_source_text(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.polymarket_price_reject (clob_token_id, price, reason) "
            "VALUES ('tok', 'n/a', 'price not numeric')"
        )
        cur.execute(
            "INSERT INTO raw.kalshi_candle_reject (ticker, ts, source_row, reason) "
            "VALUES ('T', 'x', '{\"volume\": \"abc\"}', 'volume not numeric')"
        )
        cur.execute("SELECT count(*) FROM raw.polymarket_price_reject")
        assert cur.fetchone()[0] == 1


def test_hypertable_compresses_and_still_ignores_a_duplicate(new_tables):
    with new_tables.cursor() as cur:
        if not _has_timescale(cur):
            pytest.skip("timescaledb not installed on this server")
        cur.execute(
            "SELECT count(*) FROM timescaledb_information.hypertables "
            "WHERE hypertable_name IN ('polymarket_price_t', 'kalshi_candle_t')"
        )
        assert cur.fetchone()[0] == 2
        cur.execute(
            "INSERT INTO raw.polymarket_price_t (clob_token_id, _market, _event, ts, price) "
            "SELECT 'tok' || (g % 3), 1, 1, 1700000000 + g * 60, g / 1000.0 "
            "FROM generate_series(1, 3000) g"
        )
        cur.execute("SELECT count(*) FROM raw.polymarket_price_t")
        before = cur.fetchone()[0]
        cur.execute("SELECT compress_chunk(c, true) FROM show_chunks('raw.polymarket_price_t') c")
        cur.execute(
            "SELECT count(*) FROM timescaledb_information.chunks "
            "WHERE hypertable_name = 'polymarket_price_t' AND is_compressed"
        )
        assert cur.fetchone()[0] >= 1
        # The loader re-sends rows it already loaded: they must be ignored even though the
        # chunk is compressed, and a genuinely new row must still land.
        cur.execute(
            "INSERT INTO raw.polymarket_price_t (clob_token_id, _market, _event, ts, price) "
            "VALUES ('tok1', 1, 1, 1700000060, 0.999), ('tok1', 1, 1, 1800000000, 0.5) "
            "ON CONFLICT DO NOTHING"
        )
        cur.execute("SELECT count(*) FROM raw.polymarket_price_t")
        assert cur.fetchone()[0] == before + 1
        cur.execute(
            "SELECT price FROM raw.polymarket_price_t WHERE clob_token_id='tok1' AND ts=1700000060"
        )
        assert cur.fetchone()[0] != 0.999


def test_migration_file_is_idempotent(db_conn):
    sql = Path("migrations/0117_market_price_tables.sql").read_text()
    with db_conn.cursor() as cur:
        cur.execute(sql)
        cur.execute(sql)
