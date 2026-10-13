"""Lahman on the staged layer (dlt-ingestion-layer 4.1). Same tables and file names as
``connectors.lahman``; reads the same local zip; values are the source text (the old
path lets pandas infer, which turns integers with blanks into ``5.0``)."""

import hashlib
import zipfile
from collections.abc import Callable
from pathlib import Path

import psycopg

from mlb_baseball.connectors import lahman as old
from mlb_baseball.ingest_layer import schemas
from mlb_baseball.ingest_layer.sources.csv_tables import land_snapshot, read_csv_text
from mlb_baseball.market_store import MarketTable


def _undeclared(table: str, prefix: str | None, suffix: str) -> MarketTable:
    """A table without a declared schema is landed as text (reported, never dropped)."""
    name = (table.replace("raw.lahman_", prefix) if prefix else table) + suffix
    return MarketTable(name=name, reject=name + "_reject", columns=(), key=())


def land_zip(
    connect: Callable[[], psycopg.Connection],
    zip_path: Path,
    *,
    table_prefix: str | None = None,
    table_suffix: str = "",
) -> dict[str, int]:
    """Land every Lahman table from ``zip_path``, one ledger item per table. Returns
    ``{table: rows inserted}``. ``table_prefix`` swaps ``raw.lahman_`` for a scratch name
    (parity tests)."""
    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    counts: dict[str, int] = {}
    specs = schemas.load(
        "lahman",
        prefix=("raw.lahman_", table_prefix) if table_prefix else None,
        suffix=table_suffix,
    )
    with zipfile.ZipFile(zip_path) as zf:
        for table, filename in old.TABLES:
            (member,) = (n for n in zf.namelist() if n.endswith(f"/{filename}") or n == filename)
            spec = specs.get(table) or _undeclared(table, table_prefix, table_suffix)
            target = spec.name
            landed = land_snapshot(
                connect,
                spec,
                read_csv_text(zf.read(member)),
                source=old.SOURCE,
                item_key=filename,
                source_url=str(zip_path),
                artifact_sha256=sha,
            )
            counts[target] = sum(landed.inserted.values())
    return counts


def propose_schema(csv_dir: Path) -> None:
    """Write ``schemas/lahman.json`` from a folder of the real Lahman CSVs (review the diff)."""
    from mlb_baseball.ingest_layer import infer

    infer.propose(
        "lahman",
        {table: read_csv_text((csv_dir / filename).read_bytes()) for table, filename in old.TABLES},
    )


def retype(
    connect: Callable[[], psycopg.Connection], zip_path: Path, *, apply: bool = False
) -> list:
    """Typed copies beside the live tables, compared cell by cell; with ``apply`` and no
    difference anywhere, swap ALL tables in one transaction (old tables stay as ``__old``).
    Returns one ``Difference`` per table. Safe to repeat: the ``__new`` copies are replaced."""
    from mlb_baseball.ingest_layer.swap import compare, swap

    land_zip(connect, zip_path, table_suffix="__new")
    specs = schemas.load("lahman")
    diffs = []
    with connect() as conn:
        for table, _filename in old.TABLES:
            diffs.append(compare(conn, table, table + "__new", specs[table]))
        if apply and all(d.same for d in diffs):
            for table, _filename in old.TABLES:
                swap(conn, table)
    return diffs
