"""Chadwick register on the staged layer (dlt-ingestion-layer 4.1). Same tables as
``connectors.chadwick_register``; the download stage is its ``fetch_csv`` unchanged."""

from collections.abc import Callable

import polars as pl
import psycopg

from mlb_baseball.connectors import chadwick_register as old
from mlb_baseball.ingest_layer import schemas
from mlb_baseball.ingest_layer.sources.csv_tables import land_snapshot, read_csv_text


def _frames(fetch: Callable[[str], str]) -> list[tuple[str, str, pl.DataFrame]]:
    """``(table, ledger key, frame)``; people arrive in 16 shards joined into one batch."""
    people = pl.concat(
        [read_csv_text(fetch(f"people-{shard}.csv")) for shard in old.PEOPLE_SHARDS],
        how="diagonal_relaxed",
    )
    return [("raw.register_people", "people", people)] + [
        (table, filename, read_csv_text(fetch(filename)))
        for table, filename in old.SIMPLE_TABLES.items()
    ]


def propose_schema(fetch: Callable[[str], str] = old.fetch_csv) -> None:
    """Write ``schemas/register.json`` from the real files (review the diff)."""
    from mlb_baseball.ingest_layer import infer

    infer.propose("register", {table: frame for table, _key, frame in _frames(fetch)})


def land_register(
    connect: Callable[[], psycopg.Connection],
    fetch: Callable[[str], str] = old.fetch_csv,
    *,
    table_prefix: str | None = None,
) -> dict[str, int]:
    """Replace the four register tables in one transaction. Returns ``{table: rows}``."""
    specs = schemas.load(
        "register", prefix=("raw.register_", table_prefix) if table_prefix else None
    )
    counts: dict[str, int] = {}
    with connect() as conn:  # one transaction for all four tables, like the old loader
        for table, key, frame in _frames(fetch):
            landed = land_snapshot(
                connect,
                specs[table],
                frame,
                source=old.SOURCE,
                item_key=key,
                source_url=f"{old.BASE_URL}/{key}",
                conn=conn,
            )
            counts[specs[table].name] = sum(landed.inserted.values())
    return counts
