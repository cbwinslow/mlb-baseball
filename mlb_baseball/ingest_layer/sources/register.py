"""Chadwick register on the staged layer (dlt-ingestion-layer 4.1). Same tables as
``connectors.chadwick_register``; the download stage is its ``fetch_csv`` unchanged."""

from collections.abc import Callable

import polars as pl
import psycopg

from mlb_baseball.connectors import chadwick_register as old
from mlb_baseball.ingest_layer.sources.csv_tables import land_snapshot, read_csv_text


def land_register(
    connect: Callable[[], psycopg.Connection],
    fetch: Callable[[str], str] = old.fetch_csv,
    *,
    table_prefix: str | None = None,
) -> dict[str, int]:
    """Replace the four register tables. People arrive in 16 shards that are joined into
    one batch and landed as one ledger item. Returns ``{table: rows inserted}``."""

    def named(table: str) -> str:
        return table if table_prefix is None else table.replace("raw.register_", table_prefix)

    counts: dict[str, int] = {}
    people = pl.concat(
        [read_csv_text(fetch(f"people-{shard}.csv")) for shard in old.PEOPLE_SHARDS],
        how="diagonal_relaxed",
    )
    jobs = [("raw.register_people", "people", people)] + [
        (table, filename, read_csv_text(fetch(filename)))
        for table, filename in old.SIMPLE_TABLES.items()
    ]
    with connect() as conn:  # one transaction for all four tables, like the old loader
        for table, key, frame in jobs:
            landed = land_snapshot(
                connect,
                named(table),
                frame,
                source=old.SOURCE,
                item_key=key,
                source_url=f"{old.BASE_URL}/{key}",
                conn=conn,
            )
            counts[named(table)] = sum(landed.inserted.values())
    return counts
