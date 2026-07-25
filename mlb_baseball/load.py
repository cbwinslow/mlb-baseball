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
from psycopg import sql

_IDENTIFIER_RE = re.compile(r"[^a-z0-9_]")


def _pg_column_name(name: str) -> str:
    """Postgres-idiomatic column name: lowercased, non-alphanumeric stripped, and
    prefixed if it would otherwise start with a digit (e.g. Lahman's "2B"/"3B"
    columns). Case-folding only — no semantic change from the source
    (e.g. playerID -> playerid)."""
    cleaned = _IDENTIFIER_RE.sub("_", name.lower())
    return f"n{cleaned}" if cleaned[0].isdigit() else cleaned


def _table_identifier(table: str) -> sql.Identifier:
    return sql.Identifier(*table.split("."))


def load_dataframe(
    conn: psycopg.Connection,
    table: str,
    df: pd.DataFrame,
    *,
    scope_column: str | None = None,
    scope_value: str | None = None,
) -> int:
    """Creates `table` if needed (schema derived from df's columns) and loads df into
    it. Default replace strategy is a full TRUNCATE — right for sources small enough
    to reload whole (the register, Lahman). For sources landed in independent chunks
    (e.g. Retrosheet, one season at a time), pass scope_column/scope_value to replace
    only rows matching that value, leaving every other chunk's data alone — a full
    TRUNCATE on every call would wipe out all previously loaded seasons.
    scope_column must already be a sanitized column name (e.g. "_season").

    Column identifiers are always quoted (via psycopg.sql.Identifier) — raw sources
    sometimes use reserved SQL keywords as column names (e.g. Retrosheet's
    parkcode.txt has a column literally named "end"; found by actually running
    this against real data, not by inspection).

    When scope_column is given, an index on it is created (once, IF NOT EXISTS)
    right after the table — otherwise every per-chunk DELETE is a full sequential
    scan, and gets slower as the table grows. Found the hard way: retrosheet's
    bootstrap looked "stuck" partway through — it wasn't, a DELETE against a
    9GB, un-indexed raw.retrosheet_plays was just taking longer each year.

    A later call's DataFrame can have columns an earlier one didn't — e.g.
    retrosheet_box.py's game rows come from cwbox's XML output, which only
    includes attributes actually present for a given game (some historical
    games have extra umpire positions others don't), so different years'
    DataFrames can genuinely differ in shape. Missing columns are added via
    ALTER TABLE rather than failing on COPY; found by a real bootstrap
    crashing partway through on "column ... does not exist", not designed
    in advance."""
    columns = [_pg_column_name(c) for c in df.columns]
    table_ident = _table_identifier(table)
    with conn.cursor() as cur:
        column_defs = sql.SQL(", ").join(
            sql.SQL("{} text").format(sql.Identifier(c)) for c in columns
        )
        cur.execute(
            sql.SQL(
                "CREATE TABLE IF NOT EXISTS {table} "
                "({column_defs}, _loaded_at timestamptz NOT NULL DEFAULT now())"
            ).format(table=table_ident, column_defs=column_defs)
        )
        schema, bare_table = table.split(".")
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s",
            (schema, bare_table),
        )
        existing_columns = {row[0] for row in cur.fetchall()}
        for column in columns:
            if column not in existing_columns:
                cur.execute(
                    sql.SQL("ALTER TABLE {table} ADD COLUMN {col} text").format(
                        table=table_ident, col=sql.Identifier(column)
                    )
                )
        if scope_column is None:
            cur.execute(sql.SQL("TRUNCATE {table}").format(table=table_ident))
        else:
            index_name = f"{table.split('.')[-1]}_{scope_column}_idx"
            cur.execute(
                sql.SQL("CREATE INDEX IF NOT EXISTS {index} ON {table} ({col})").format(
                    index=sql.Identifier(index_name),
                    table=table_ident,
                    col=sql.Identifier(scope_column),
                )
            )
            cur.execute(
                sql.SQL("DELETE FROM {table} WHERE {col} = %s").format(
                    table=table_ident, col=sql.Identifier(scope_column)
                ),
                (scope_value,),
            )
        csv_text = df.to_csv(index=False, header=False)
        column_list = sql.SQL(", ").join(sql.Identifier(c) for c in columns)
        copy_sql = sql.SQL("COPY {table} ({columns}) FROM STDIN WITH (FORMAT csv)").format(
            table=table_ident, columns=column_list
        )
        with cur.copy(copy_sql) as copy:
            copy.write(csv_text)
        return cur.rowcount
