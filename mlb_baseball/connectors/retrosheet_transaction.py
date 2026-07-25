"""Lands Retrosheet's transaction database (retrosheet.org/transactions/
tranDB.zip) into raw.retrosheet_transaction: trades, sales, releases,
waivers, free agency, DL/IL placements, call-ups, draft picks, etc.

Retrosheet froze this database as of November 26, 2021 and transferred
ongoing maintenance to Baseball-Reference — this connector's update() is
therefore a no-op (nothing to refresh; use MLB Stats API or a future
Baseball-Reference connector for anything after the freeze date). Documented
here rather than silently pretending this source stays current.

tran.txt is headerless; the 16-field layout is documented in the zip's own
readme.txt (bundled but not loaded — it's documentation, not data) and
confirmed against a real downloaded file before hardcoding.
"""

import zipfile

import pandas as pd
import psycopg

from mlb_baseball import manifest
from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_last_run, check_table_has_rows
from mlb_baseball.ingest import track_run
from mlb_baseball.load import load_dataframe

SOURCE = "retrosheet_transaction"
TABLE = "raw.retrosheet_transaction"
TRANSACTION_FIELDS = [
    "primary_date",
    "time",
    "primary_date_approx",
    "secondary_date",
    "secondary_date_approx",
    "transaction_id",
    "player_id",
    "type",
    "from_team",
    "from_league",
    "to_team",
    "to_league",
    "draft_type",
    "draft_round",
    "pick_number",
    "info",
]


def _transactions() -> pd.DataFrame:
    path = manifest.download(
        SOURCE, "tranDB.zip", "https://www.retrosheet.org/transactions/tranDB.zip"
    )
    with zipfile.ZipFile(path) as zf:
        with zf.open("tran.txt") as f:
            df = pd.read_csv(f, header=None, names=TRANSACTION_FIELDS, low_memory=False)
    manifest.mark_status(SOURCE, path.name, "loaded")
    return df


def _run(conn: psycopg.Connection) -> dict[str, int]:
    return {TABLE: load_dataframe(conn, TABLE, _transactions())}


def bootstrap() -> dict[str, int]:
    with get_connection() as conn, track_run(conn, SOURCE, "bootstrap") as result:
        counts = _run(conn)
        conn.commit()
        result["rows"] = sum(counts.values())
    return counts


def update() -> dict[str, int]:
    """Frozen source (see module docstring) — re-runs the same full load as
    bootstrap() rather than a no-op, in case Retrosheet ever corrects the
    archive in place; harmless and idempotent either way."""
    with get_connection() as conn, track_run(conn, SOURCE, "update") as result:
        counts = _run(conn)
        conn.commit()
        result["rows"] = sum(counts.values())
    return counts


def health_check() -> list[Check]:
    return [check_table_has_rows(TABLE), check_last_run(SOURCE)]
