"""Generic loader for pandas-DataFrame-shaped sources (pybaseball-backed connectors).

Complements the CSV+COPY pattern used by connectors that fetch raw text directly
(e.g. chadwick_register). Table schema is derived from the DataFrame itself rather
than a hand-written migration — impractical to hand-author migrations for the ~27
Lahman tables individually, and pandas is already the source of truth for their
shape. See docs/ARCHITECTURE.md "Loading patterns".
"""

import re

import pandas as pd
import psycopg

_IDENTIFIER_RE = re.compile(r"[^a-z0-9_]")


def _pg_column_name(name: str) -> str:
    """Postgres-idiomatic column name: lowercased, non-alphanumeric stripped, and
    prefixed if it would otherwise start with a digit (e.g. Lahman's "2B"/"3B"
    columns). Case-folding only — no semantic change from the source
    (e.g. playerID -> playerid)."""
    cleaned = _IDENTIFIER_RE.sub("_", name.lower())
    return f"n{cleaned}" if cleaned[0].isdigit() else cleaned


def load_dataframe(conn: psycopg.Connection, table: str, df: pd.DataFrame) -> int:
    columns = [_pg_column_name(c) for c in df.columns]
    column_defs = ", ".join(f"{c} text" for c in columns)
    with conn.cursor() as cur:
        cur.execute(
            f"CREATE TABLE IF NOT EXISTS {table} "
            f"({column_defs}, _loaded_at timestamptz NOT NULL DEFAULT now())"
        )
        cur.execute(f"TRUNCATE {table}")
        csv_text = df.to_csv(index=False, header=False)
        column_list = ", ".join(columns)
        copy_sql = f"COPY {table} ({column_list}) FROM STDIN WITH (FORMAT csv)"
        with cur.copy(copy_sql) as copy:
            copy.write(csv_text)
        return cur.rowcount
