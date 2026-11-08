"""Spike (dlt-ingestion-layer 1.4): rows/s of the dlt path against the current Polymarket
price loader, on payloads shaped like `POST /batch-prices-history` replies (no network).
Prints timings (run with -s); asserts only that both paths land the same rows."""

import dataclasses
import random
import time

import polars as pl
import psycopg

from mlb_baseball import market_store
from mlb_baseball.ingest_layer.land import ITEM, Item, Policy, land

BATCHES, TOKENS, POINTS = 10, 20, 500  # 100k rows over 10 batches of 10k
TABLE = dataclasses.replace(
    market_store.POLYMARKET_PRICE,
    name="raw.polymarket_price_b",
    reject="raw.polymarket_price_reject",
)


def _payload(batch: int) -> dict[str, list[dict]]:
    rng = random.Random(batch)
    return {
        f"tok{batch}-{t}": [{"t": 1_700_000_000 + i * 60, "p": rng.random()} for i in range(POINTS)]
        for t in range(TOKENS)
    }


def _frame(b: int) -> pl.DataFrame:
    payload = _payload(b)
    n = TOKENS * POINTS
    return pl.DataFrame(
        {
            ITEM: [str(b)] * n,
            "clob_token_id": [tok for tok, pts in payload.items() for _ in pts],
            "_market": ["1"] * n,
            "_event": ["1"] * n,
            "ts": [str(p["t"]) for pts in payload.values() for p in pts],
            "price": [str(p["p"]) for pts in payload.values() for p in pts],
        }
    )


def _count(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.polymarket_price_b")
        n = cur.fetchone()[0]
    conn.rollback()
    return n


def test_dlt_path_vs_current_loader(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT meta.create_market_tables('_b')")
    db_conn.commit()
    cols = ["clob_token_id", "_market", "_event", "ts", "price"]
    total = BATCHES * TOKENS * POINTS

    start = time.perf_counter()
    for b in range(BATCHES):
        csv = "".join(
            f"{tok},1,1,{p['t']},{p['p']}\n" for tok, pts in _payload(b).items() for p in pts
        )
        market_store.append_rows(db_conn, TABLE, cols, csv)
        db_conn.commit()
    old = time.perf_counter() - start
    assert _count(db_conn) == total
    with db_conn.cursor() as cur:
        cur.execute("TRUNCATE raw.polymarket_price_b")
    db_conn.commit()

    info = db_conn.info
    start = time.perf_counter()
    for b in range(BATCHES):
        frame = _frame(b)
        land(
            lambda: psycopg.connect(info.dsn, password=info.password),
            TABLE,
            Policy.APPEND,
            frame,
            source="bench",
            dataset="polymarket_price",
            items=[Item(str(b))],
        )
    new = time.perf_counter() - start
    assert _count(db_conn) == total

    with db_conn.cursor() as cur:
        cur.execute("TRUNCATE raw.polymarket_price_b")
    db_conn.commit()
    frames = [_frame(b) for b in range(BATCHES)]
    start = time.perf_counter()
    land(
        lambda: psycopg.connect(info.dsn, password=info.password),
        TABLE,
        Policy.APPEND,
        pl.concat(frames),
        source="bench",
        dataset="polymarket_price",
        items=[Item(str(b)) for b in range(BATCHES)],
    )
    one_call = time.perf_counter() - start
    assert _count(db_conn) == total
    print(f"\nBENCH one call, {BATCHES} items: {total / one_call:,.0f} rows/s ({one_call:.2f}s)")
    print(
        f"\nBENCH rows={total} current={total / old:,.0f} rows/s ({old:.2f}s) "
        f"dlt={total / new:,.0f} rows/s ({new:.2f}s)"
    )
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE raw.polymarket_price_b")
        cur.execute("DELETE FROM meta.ingestion_item WHERE source = 'bench'")
    db_conn.commit()
