"""Lands the Chadwick Bureau Register (ID crosswalk) into raw.register_*.

The register is a point-in-time snapshot, not an event stream, so bootstrap and
update are the same operation here — both truncate and reload every table, safe
to re-run, never duplicates rows. Sources with real incremental behavior (e.g.
Statcast, MLB Stats API) implement bootstrap()/update() differently; this one
is the degenerate case. See docs/ARCHITECTURE.md "Connector contract" and
migrations/0002_chadwick_register_raw.sql.
"""

import csv
import io

import psycopg
import requests

from mlb_baseball.db import get_connection
from mlb_baseball.health import (
    DAILY_FRESHNESS_THRESHOLD_MINUTES,
    Check,
    check_last_run,
    check_recent_run,
    check_table_has_rows,
)
from mlb_baseball.ingest import track_run

SOURCE = "register"
FRESHNESS_THRESHOLD_MINUTES = DAILY_FRESHNESS_THRESHOLD_MINUTES

BASE_URL = "https://raw.githubusercontent.com/chadwickbureau/register/master/data"
PEOPLE_SHARDS = "0123456789abcdef"

# (table, source filename(s)) — people is sharded across 16 files, the rest are single files.
SIMPLE_TABLES = {
    "raw.register_names": "names.csv",
    "raw.register_links": "links.csv",
    "raw.register_countries": "countries.csv",
}


def fetch_csv(filename: str) -> str:
    response = requests.get(f"{BASE_URL}/{filename}", timeout=30)
    response.raise_for_status()
    return response.text


def extract_columns(csv_text: str) -> list[str]:
    """Column names from the CSV header row, in order."""
    header_line = csv_text.splitlines()[0]
    return next(csv.reader(io.StringIO(header_line)))


def load_csv(conn: psycopg.Connection, table: str, csv_text: str) -> int:
    """COPY a CSV's rows into `table`. Column list comes from the CSV header itself,
    since every raw table here is designed to mirror its source file's columns exactly
    (see migrations/0002_chadwick_register_raw.sql) — trusted because the source is a
    pinned URL under our control, not arbitrary input."""
    columns = extract_columns(csv_text)
    column_list = ", ".join(columns)
    copy_sql = f"COPY {table} ({column_list}) FROM STDIN WITH (FORMAT csv, HEADER true)"
    with conn.cursor() as cur:
        with cur.copy(copy_sql) as copy:
            copy.write(csv_text)
        return cur.rowcount


def _run(mode: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    with get_connection() as conn, track_run(conn, SOURCE, mode) as result:
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE raw.register_people, "
                "raw.register_names, "
                "raw.register_links, "
                "raw.register_countries"
            )

        people_total = 0
        for shard in PEOPLE_SHARDS:
            csv_text = fetch_csv(f"people-{shard}.csv")
            people_total += load_csv(conn, "raw.register_people", csv_text)
        counts["raw.register_people"] = people_total

        for table, filename in SIMPLE_TABLES.items():
            csv_text = fetch_csv(filename)
            counts[table] = load_csv(conn, table, csv_text)

        conn.commit()
        result["rows"] = sum(counts.values())
    return counts


def bootstrap() -> dict[str, int]:
    return _run("bootstrap")


def update() -> dict[str, int]:
    return _run("update")


def health_check() -> list[Check]:
    return [
        check_table_has_rows("raw.register_people"),
        check_last_run(SOURCE),
        check_recent_run(SOURCE, FRESHNESS_THRESHOLD_MINUTES),
    ]
