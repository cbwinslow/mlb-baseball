"""Spike (dlt-ingestion-layer 1.4): rows/s of the dlt path against the current Polymarket
price loader, on payloads shaped like `POST /batch-prices-history` replies (no network).
Prints timings (run with -s); asserts only that both paths land the same rows."""

import dataclasses
import random
import time

import dlt
import polars as pl
import psycopg

from mlb_baseball import market_store
from mlb_baseball.ingest_layer.destination import item_destination

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


def _count(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.polymarket_price_b")
        n = cur.fetchone()[0]
    conn.rollback()
    return n


def test_dlt_path_vs_current_loader(db_conn, tmp_path):
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
        payload = _payload(b)
        rows = pl.DataFrame(
            {
                "clob_token_id": [tok for tok, pts in payload.items() for _ in pts],
                "_market": pl.Series([1] * (TOKENS * POINTS), dtype=pl.Int32),
                "_event": pl.Series([1] * (TOKENS * POINTS), dtype=pl.Int32),
                "ts": [p["t"] for pts in payload.values() for p in pts],
                "price": [p["p"] for pts in payload.values() for p in pts],
            }
        ).to_arrow()  # typed columnar batch: dlt skips its slow per-dict normalization
        dest = item_destination(
            lambda: psycopg.connect(info.dsn, password=info.password),
            target=TABLE.name,
            key=TABLE.key,
            source="bench",
            dataset="polymarket_price",
            item_key=str(b),
        )
        pipe = dlt.pipeline("bench", destination=dest, pipelines_dir=str(tmp_path / str(b)))
        pipe.run(rows, table_name="polymarket_price", loader_file_format="parquet")
    new = time.perf_counter() - start
    assert _count(db_conn) == total

    print(
        f"\nBENCH rows={total} current={total / old:,.0f} rows/s ({old:.2f}s) "
        f"dlt={total / new:,.0f} rows/s ({new:.2f}s)"
    )
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE raw.polymarket_price_b")
        cur.execute("DELETE FROM meta.ingestion_item WHERE source = 'bench'")
    db_conn.commit()
