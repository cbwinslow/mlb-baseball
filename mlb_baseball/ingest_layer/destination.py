"""A ``dlt`` destination that lands one ledger item atomically.

``dlt`` extracts and normalizes the payload into a parquet file; this destination reads
that file with pyarrow and, in ONE PostgreSQL transaction, inserts the rows and upserts
the item's ``meta.ingestion_item`` row. Any failure rolls both back, so a ledger row never
claims rows that are not there. The caller runs one pipeline per ledger item.
"""

import io
from collections.abc import Callable
from typing import Any

import dlt
import psycopg
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
from psycopg import sql

_LEDGER_UPSERT = """
INSERT INTO meta.ingestion_item (source, dataset, item_key, status, rows, parser_version)
VALUES (%s, %s, %s, 'loaded', %s, %s)
ON CONFLICT (source, dataset, item_key) DO UPDATE
   SET status = 'loaded', rows = EXCLUDED.rows, parser_version = EXCLUDED.parser_version,
       updated_at = now()
"""


def item_destination(
    connect: Callable[[], psycopg.Connection],
    *,
    target: str,
    key: tuple[str, ...],
    source: str,
    dataset: str,
    item_key: str,
    parser_version: str | None = None,
):
    """Build a destination bound to one ledger item. ``target`` is ``schema.table``;
    ``key`` is its conflict key (rows already present are skipped)."""

    schema, table = target.split(".")

    @dlt.destination(batch_size=0, loader_file_format="parquet", naming_convention="direct")
    def land(path: Any, dlt_table: Any, /) -> None:  # batch_size=0: a parquet file path
        data = pq.read_table(path)
        cols = [c for c in data.column_names if not c.startswith("_dlt_")]  # tool bookkeeping
        quoted = sql.SQL(", ").join(map(sql.Identifier, cols))
        stage = sql.Identifier("_ingest_stage")
        merge = sql.SQL(
            "INSERT INTO {t} ({c}) SELECT {c} FROM {s} ON CONFLICT ({k}) DO NOTHING"
        ).format(
            t=sql.Identifier(schema, table),
            c=quoted,
            s=stage,
            k=sql.SQL(", ").join(map(sql.Identifier, key)),
        )
        with connect() as conn:  # commit on clean exit, rollback on exception
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        "CREATE TEMP TABLE {s} ON COMMIT DROP AS SELECT {c} FROM {t} WITH NO DATA"
                    ).format(s=stage, c=quoted, t=sql.Identifier(schema, table))
                )
                buf = io.BytesIO()
                pacsv.write_csv(
                    data.select(cols),
                    buf,
                    pacsv.WriteOptions(include_header=False, quoting_style="needed"),
                )
                with cur.copy(
                    sql.SQL("COPY {s} ({c}) FROM STDIN WITH (FORMAT csv)").format(s=stage, c=quoted)
                ) as cp:
                    cp.write(buf.getvalue())
                cur.execute(merge)
                cur.execute(
                    _LEDGER_UPSERT, (source, dataset, item_key, data.num_rows, parser_version)
                )

    return land
