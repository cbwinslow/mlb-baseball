"""Shared by the single-file CSV sources (register, lahman): a CSV becomes an all-text
polars frame with the project's column-name sanitizing, landed whole (TRUNCATE) as one
ledger item."""

import io
from collections.abc import Callable
from datetime import datetime

import polars as pl
import psycopg

from mlb_baseball.ingest_layer.land import ITEM, Item, Landed, Policy, land
from mlb_baseball.load import pg_column_name
from mlb_baseball.market_store import MarketTable


def read_csv_text(source: bytes | str) -> pl.DataFrame:
    """Every value as the source text (nothing inferred), headers sanitized like ``load.py``."""
    raw = source.encode() if isinstance(source, str) else source
    frame = pl.read_csv(io.BytesIO(raw), infer_schema=False)
    names = [pg_column_name(c) for c in frame.columns]
    if len(set(names)) != len(names):
        raise ValueError(f"source columns collide after sanitization: {names}")
    return frame.rename(dict(zip(frame.columns, names, strict=True)))


def land_snapshot(
    connect: Callable[[], psycopg.Connection],
    table: str,
    frame: pl.DataFrame,
    *,
    source: str,
    item_key: str,
    source_url: str | None = None,
    artifact_sha256: str | None = None,
    retrieved_at: datetime | None = None,
    parser_version: str = "csv_tables/1",
    conn: psycopg.Connection | None = None,
) -> Landed:
    """Replace ``table`` with ``frame`` (a full snapshot) and record one ledger item."""
    spec = MarketTable(name=table, reject=table, columns=(), key=())
    item = Item(
        item_key,
        source_url=source_url,
        artifact_sha256=artifact_sha256,
        parser_version=parser_version,
        retrieved_at=retrieved_at,
    )
    return land(
        connect,
        spec,
        Policy.TRUNCATE,
        frame.with_columns(pl.lit(item_key).alias(ITEM)),
        source=source,
        dataset=table,
        items=[item],
        conn=conn,
    )
