"""market_store.append_rows against real PostgreSQL (plain and, when present, hypertable)."""

import pytest

from mlb_baseball import market_store as ms


@pytest.fixture
def tables(db_conn):
    # Fresh typed tables under the real names (the test database has none: the loaders
    # create them dynamically elsewhere, and other tests drop them).
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.polymarket_price, raw.kalshi_candle CASCADE")
    ms.ensure_store(db_conn)
    yield db_conn
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.polymarket_price, raw.kalshi_candle CASCADE")
        cur.execute("TRUNCATE raw.polymarket_price_reject, raw.kalshi_candle_reject")
    db_conn.commit()


PM_COLS = ["clob_token_id", "_market", "_event", "ts", "price"]


def test_polymarket_rows_are_typed_and_second_load_changes_nothing(tables):
    csv = "tokA,1,2,1700000000,0.5\ntokA,1,2,1700000060,0.51\n"
    first = ms.append_rows(tables, ms.POLYMARKET_PRICE, PM_COLS, csv)
    second = ms.append_rows(tables, ms.POLYMARKET_PRICE, PM_COLS, csv)
    assert first == (2, 0)
    assert second == (0, 0)
    with tables.cursor() as cur:
        cur.execute("SELECT count(*), sum(price) FROM raw.polymarket_price")
        assert cur.fetchone() == (2, pytest.approx(1.01))
        cur.execute(
            "SELECT pg_typeof(ts)::text, pg_typeof(price)::text FROM raw.polymarket_price LIMIT 1"
        )
        assert cur.fetchone() == ("bigint", "double precision")


def test_bad_polymarket_value_is_rejected_and_the_rest_loads(tables):
    csv = (
        "tokA,1,2,1700000000,0.5\n"
        "tokA,1,2,1700000060,n/a\n"
        "tokA,x,2,1700000120,0.4\n"
        ",1,2,1700000180,0.3\n"
    )
    inserted, rejected = ms.append_rows(tables, ms.POLYMARKET_PRICE, PM_COLS, csv)
    assert (inserted, rejected) == (1, 3)
    with tables.cursor() as cur:
        cur.execute("SELECT price, reason FROM raw.polymarket_price_reject ORDER BY ts")
        rows = cur.fetchall()
    assert rows[0] == ("n/a", "price is not a valid double precision")
    assert rows[1][1] == "_market is not a valid integer"
    assert rows[2][1] == "clob_token_id is empty"


def test_empty_price_is_null_not_zero(tables):
    ms.append_rows(tables, ms.POLYMARKET_PRICE, PM_COLS, "tokA,1,2,1700000000,\n")
    with tables.cursor() as cur:
        cur.execute("SELECT price IS NULL FROM raw.polymarket_price")
        assert cur.fetchone()[0] is True


def test_kalshi_candle_empty_dollars_is_null_and_bad_value_goes_to_reject_as_json(tables):
    cols = ["ticker", "ts", "volume", "price_close_dollars"]
    csv = "KX-1,1700000000,12.00,\nKX-2,1700000060,3.00,0.4200\nKX-3,1700000120,abc,0.1\n"
    inserted, rejected = ms.append_rows(tables, ms.KALSHI_CANDLE, cols, csv)
    assert (inserted, rejected) == (2, 1)
    with tables.cursor() as cur:
        cur.execute("SELECT price_close_dollars IS NULL FROM raw.kalshi_candle WHERE ticker='KX-1'")
        assert cur.fetchone()[0] is True
        cur.execute("SELECT ticker, source_row->>'volume', reason FROM raw.kalshi_candle_reject")
        assert cur.fetchone() == ("KX-3", "abc", "volume is not a valid numeric(14,2)")


def test_kalshi_exact_duplicate_in_one_batch_loads_once(tables):
    cols = ["ticker", "ts", "price_close_dollars"]
    csv = "KX-1,1700000000,0.5000\nKX-1,1700000000,0.5000\n"
    assert ms.append_rows(tables, ms.KALSHI_CANDLE, cols, csv) == (1, 0)


def test_out_of_range_number_is_rejected_not_an_error(tables):
    cols = ["ticker", "ts", "price_close_dollars"]
    inserted, rejected = ms.append_rows(
        tables, ms.KALSHI_CANDLE, cols, "KX-1,1700000000,99999999.5\n"
    )
    assert (inserted, rejected) == (0, 1)


def test_new_source_field_is_added_as_text_and_kept(tables):
    missing = ms.missing_columns(tables, ms.KALSHI_CANDLE, ["ticker", "ts", "brand_new"])
    assert missing == ["brand_new"]
    ms.add_text_columns(tables, ms.KALSHI_CANDLE, missing)
    ms.append_rows(
        tables, ms.KALSHI_CANDLE, ["ticker", "ts", "brand_new"], "KX-1,1700000000,hello\n"
    )
    with tables.cursor() as cur:
        cur.execute("SELECT brand_new FROM raw.kalshi_candle")
        assert cur.fetchone()[0] == "hello"


def test_empty_input_does_nothing(tables):
    assert ms.append_rows(tables, ms.POLYMARKET_PRICE, PM_COLS, "") == (0, 0)


def test_doctor_check_flags_recent_rejects_and_passes_when_none(tables):
    from mlb_baseball.health import check_reject_table

    ok = check_reject_table("raw.polymarket_price_reject")
    assert ok.ok
    ms.append_rows(tables, ms.POLYMARKET_PRICE, PM_COLS, "tokA,1,2,1700000000,n/a\n")
    tables.commit()
    bad = check_reject_table("raw.polymarket_price_reject")
    assert not bad.ok and "price is not a valid double precision" in bad.detail
