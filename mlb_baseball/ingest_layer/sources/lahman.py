"""Lahman on the staged layer (dlt-ingestion-layer 4.1). Same tables and file names as
``connectors.lahman``; reads the same local zip; values are the source text (the old
path lets pandas infer, which turns integers with blanks into ``5.0``)."""

import hashlib
import zipfile
from collections.abc import Callable
from pathlib import Path

import psycopg

from mlb_baseball.connectors import lahman as old
from mlb_baseball.ingest_layer.sources.csv_tables import land_snapshot, read_csv_text


def land_zip(
    connect: Callable[[], psycopg.Connection],
    zip_path: Path,
    *,
    table_prefix: str | None = None,
) -> dict[str, int]:
    """Land every Lahman table from ``zip_path``, one ledger item per table. Returns
    ``{table: rows inserted}``. ``table_prefix`` swaps ``raw.lahman_`` for a scratch name
    (parity tests)."""
    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    counts: dict[str, int] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for table, filename, _fetch in old.TABLES:
            (member,) = (n for n in zf.namelist() if n.endswith(f"/{filename}") or n == filename)
            target = table if table_prefix is None else table.replace("raw.lahman_", table_prefix)
            landed = land_snapshot(
                connect,
                target,
                read_csv_text(zf.read(member)),
                source=old.SOURCE,
                item_key=filename,
                source_url=str(zip_path),
                artifact_sha256=sha,
            )
            counts[target] = sum(landed.inserted.values())
    return counts
