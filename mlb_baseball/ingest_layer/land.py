"""Land typed batches into PostgreSQL through ``dlt``, one transaction per call (D10).

``dlt`` extracts and normalizes the frame into parquet files in a throwaway state folder;
a collector destination reads them back; nothing touches the database until ``dlt`` has
finished, so a failed or half-finished load package can never reach PostgreSQL or be
retried under another item. Then ONE transaction: apply the landing policy, write rejects,
and upsert one ``meta.ingestion_item`` row per item with the rows actually inserted. An item
with no rows still gets its policy applied (a scoped replace deletes) and its ledger row.
"""

import io
import json
import logging
import tempfile
from collections import Counter
from collections.abc import Callable, Sequence
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import dlt
import polars as pl
import psycopg
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
from psycopg import sql

from mlb_baseball.ingest_layer.state import state_dir as default_state_dir
from mlb_baseball.ingest_layer.types import cast
from mlb_baseball.market_store import MarketTable, missing_columns

log = logging.getLogger(__name__)

ITEM = "_item"  # frame column naming the ledger item each row belongs to


class Policy(Enum):
    APPEND = "append"  # insert, skip rows whose key exists
    UPSERT = "upsert"  # insert, update non-key columns when the key exists
    REPLACE_SCOPE = "replace_scope"  # delete each item's scope, then insert
    TRUNCATE = "truncate"  # empty the table, then insert


@dataclass(frozen=True)
class Item:
    """One ledger item. ``scope`` (column -> value) is what REPLACE_SCOPE deletes first."""

    key: str
    scope: dict[str, Any] = field(default_factory=dict)
    source_url: str | None = None
    artifact_sha256: str | None = None
    run_id: int | None = None
    schema_fingerprint: str | None = None
    parser_version: str | None = None
    retrieved_at: datetime | None = None  # download time, not load time


@dataclass
class Landed:
    inserted: dict[str, int]
    rejected: int
    new_columns: list[str]


_LEDGER = """
INSERT INTO meta.ingestion_item (source, dataset, item_key, status, rows, source_url,
    artifact_sha256, run_id, schema_fingerprint, parser_version, retrieved_at)
VALUES (%s, %s, %s, 'loaded', %s, %s, %s, %s, %s, %s, COALESCE(%s, now()))
ON CONFLICT (source, dataset, item_key) DO UPDATE
   SET status = 'loaded', rows = EXCLUDED.rows, source_url = EXCLUDED.source_url,
       artifact_sha256 = EXCLUDED.artifact_sha256, run_id = EXCLUDED.run_id,
       schema_fingerprint = EXCLUDED.schema_fingerprint,
       parser_version = EXCLUDED.parser_version, retrieved_at = EXCLUDED.retrieved_at,
       error = NULL, updated_at = now()
"""


def _normalize(frame: pl.DataFrame, state: Path) -> pa.Table:
    """Run the frame through dlt (extract + normalize + file jobs) and read the files back."""
    seen: list[pa.Table] = []

    @dlt.destination(batch_size=0, loader_file_format="parquet", naming_convention="direct")
    def collect(path: Any, table: Any, /) -> None:
        seen.append(pq.read_table(path))

    pipe = dlt.pipeline("land", destination=collect, pipelines_dir=str(state))
    try:
        pipe.run(frame.to_arrow(), table_name="batch", loader_file_format="parquet")
    finally:
        pipe.abort_packages()
    if not seen:
        return frame.to_arrow().slice(0, 0)
    return pa.concat_tables(seen)


def land(
    connect: Callable[[], psycopg.Connection],
    table: MarketTable,
    policy: Policy,
    frame: pl.DataFrame,
    *,
    source: str,
    dataset: str,
    items: Sequence[Item],
    state_dir: Path | None = None,
    conn: psycopg.Connection | None = None,
) -> Landed:
    """Cast ``frame`` (source values; an ``_item`` column names each row's item), push it
    through dlt, and land it in one transaction. Raises before any write if dlt fails.
    Pass ``conn`` to join the caller's transaction (several tables, all or nothing): then
    nothing is committed here and the caller commits or rolls back."""
    declared = {i.key for i in items}
    if ITEM in frame.columns and not set(frame[ITEM].unique().to_list()) <= declared:
        raise ValueError("frame names an item that was not declared")
    if policy is Policy.REPLACE_SCOPE and any(not i.scope for i in items):
        raise ValueError("REPLACE_SCOPE needs a scope on every item")
    good, rejected = cast(frame, table)
    root = state_dir or default_state_dir()
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as folder:
        data = _normalize(good, Path(folder))
    cols = [c for c in data.column_names if not c.startswith("_dlt_") and c != ITEM]
    schema, _, rel = table.name.partition(".")
    target = sql.Identifier(schema, rel)
    inserted = dict.fromkeys(declared, 0)
    with nullcontext(conn) if conn is not None else connect() as db, db.cursor() as cur:
        if not table.columns:  # source-shaped table with no declared types: all text
            defs = sql.SQL(", ").join(sql.SQL("{} text").format(sql.Identifier(c)) for c in cols)
            cur.execute(
                sql.SQL(
                    "CREATE TABLE IF NOT EXISTS {t} "
                    "({d}, _loaded_at timestamptz NOT NULL DEFAULT now())"
                ).format(t=target, d=defs)
            )
        new = missing_columns(db, table, cols)
        if new:
            log.warning("%s: new source field(s) landed as text: %s", table.name, ", ".join(new))
        for name in new:
            cur.execute(
                sql.SQL("ALTER TABLE {} ADD COLUMN {} text").format(target, sql.Identifier(name))
            )
        if policy is Policy.TRUNCATE:
            cur.execute(sql.SQL("TRUNCATE {}").format(target))
        if policy is Policy.REPLACE_SCOPE:
            for item in items:
                where = sql.SQL(" AND ").join(
                    sql.SQL("{} IS NOT DISTINCT FROM %s").format(sql.Identifier(c))
                    for c in item.scope
                )
                cur.execute(
                    sql.SQL("DELETE FROM {} WHERE {}").format(target, where),
                    list(item.scope.values()),
                )
        if data.num_rows:
            _insert(cur, data, cols, table, policy, target, inserted)
        _write_rejects(cur, table, rejected)
        for item in items:
            cur.execute(
                _LEDGER,
                (
                    source,
                    dataset,
                    item.key,
                    inserted[item.key],
                    item.source_url,
                    item.artifact_sha256,
                    item.run_id,
                    item.schema_fingerprint,
                    item.parser_version,
                    item.retrieved_at,
                ),
            )
    return Landed(inserted, rejected.height, new)


def _insert(cur, data, cols, table, policy, target, inserted) -> None:
    have_item = ITEM in data.column_names
    stage_cols = cols + ([ITEM] if have_item else [])
    quoted = sql.SQL(", ").join(map(sql.Identifier, cols))
    defs = sql.SQL(", ").join(sql.SQL("{} text").format(sql.Identifier(c)) for c in stage_cols)
    cur.execute(sql.SQL("CREATE TEMP TABLE _stage ({})").format(defs))  # dropped below
    buf = io.BytesIO()
    pacsv.write_csv(
        data.select(stage_cols),
        buf,
        pacsv.WriteOptions(include_header=False, quoting_style="needed"),
    )
    with cur.copy(
        sql.SQL("COPY _stage ({}) FROM STDIN WITH (FORMAT csv)").format(
            sql.SQL(", ").join(map(sql.Identifier, stage_cols))
        )
    ) as cp:
        cp.write(buf.getvalue())
    typed = table.typed()
    casts = sql.SQL(", ").join(
        sql.SQL("NULLIF({c}, '')::{k} AS {c}").format(c=sql.Identifier(c), k=sql.SQL(typed[c].kind))
        if c in typed and typed[c].kind != "text"
        else sql.SQL("NULLIF({c}, '') AS {c}").format(c=sql.Identifier(c))
        for c in cols
    )
    if not table.key:  # no identity: plain insert, every row is new
        cur.execute(
            sql.SQL("INSERT INTO {t} ({c}) SELECT {casts} FROM _stage").format(
                t=target, c=quoted, casts=casts
            )
        )
        cur.execute("DROP TABLE _stage")
        if have_item:
            for item_key, count in Counter(data[ITEM].to_pylist()).items():
                if item_key in inserted:
                    inserted[item_key] = count
        return
    key = sql.SQL(", ").join(map(sql.Identifier, table.key))
    first = sql.SQL(
        "SELECT DISTINCT ON ({k}) {casts}, {item} AS _item FROM _stage ORDER BY {k}"
    ).format(k=key, casts=casts, item=sql.Identifier(ITEM) if have_item else sql.SQL("NULL"))
    if policy is Policy.UPSERT:
        updates = [c for c in cols if c not in table.key]
        action = (
            sql.SQL("DO UPDATE SET {}").format(
                sql.SQL(", ").join(
                    sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(c)) for c in updates
                )
            )
            if updates
            else sql.SQL("DO NOTHING")
        )
    else:
        action = sql.SQL("DO NOTHING")
    cur.execute(
        sql.SQL(
            "WITH d AS ({first}), ins AS (INSERT INTO {t} ({c}) SELECT {c} FROM d "
            "ON CONFLICT ({k}) {action} RETURNING {k}) "
            "SELECT d._item, count(*) FROM d JOIN ins USING ({k}) GROUP BY d._item"
        ).format(first=first, t=target, c=quoted, k=key, action=action)
    )
    counted = cur.fetchall()
    cur.execute("DROP TABLE _stage")
    for item_key, count in counted:
        if item_key in inserted:
            inserted[item_key] = count


def _write_rejects(cur: psycopg.Cursor, table: MarketTable, rejected: pl.DataFrame) -> None:
    if not rejected.height:
        return
    rows = rejected.drop(ITEM, strict=False).to_dicts()
    if table.reject_source_row:
        cur.executemany(
            sql.SQL(
                "INSERT INTO {} (ticker, ts, source_row, reason) VALUES (%s, %s, %s::jsonb, %s)"
            ).format(sql.SQL(table.reject)),
            [
                (
                    r.get("ticker"),
                    r.get("ts"),
                    json.dumps({k: v for k, v in r.items() if k != "reason"}),
                    r["reason"],
                )
                for r in rows
            ],
        )
        return
    names = [
        c for c in rejected.columns if c in {"clob_token_id", "_market", "_event", "ts", "price"}
    ]
    cur.executemany(
        sql.SQL("INSERT INTO {} ({}, reason) VALUES ({}, %s)").format(
            sql.SQL(table.reject),
            sql.SQL(", ").join(map(sql.Identifier, names)),
            sql.SQL(", ").join(sql.Placeholder() * len(names)),
        ),
        [[r[c] for c in names] + [r["reason"]] for r in rows],
    )


def table_reject(table: MarketTable) -> MarketTable:
    """The reject table as a name-only spec, so its columns can be looked up."""
    return MarketTable(name=table.reject, reject=table.reject, columns=(), key=())
