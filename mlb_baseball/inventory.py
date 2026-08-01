"""Live inventory of what's actually in the database: every raw/core/gold
table with its row count, plus the last ingestion run per source. Deliberately
not a static doc snapshot — with connectors landing dozens of tables now, a
written inventory would go stale the moment ingestion runs again. This
queries current state every time, so it's always right.
"""

import psycopg

from mlb_baseball.db import fetch_one, get_connection


def tables() -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT n.nspname, c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname IN ('raw', 'core', 'gold') AND c.relkind = 'r'
                ORDER BY 1, 2
                """
            )
            schema_tables = cur.fetchall()

        result = []
        with conn.cursor() as cur:
            for schema, table in schema_tables:
                cur.execute(f"SELECT count(*) FROM {schema}.{table}")
                (row_count,) = fetch_one(cur)
                result.append({"schema": schema, "table": table, "rows": row_count})
        return result


def last_runs() -> list[dict]:
    """Empty (not an error) if meta.ingestion_run doesn't exist yet — a
    fresh, unmigrated database genuinely has no runs to report. Run
    `mlb migrate` to create it; that's what `mlb doctor` will say too."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT DISTINCT ON (source)
                        source, mode, status, rows, started_at, finished_at
                    FROM meta.ingestion_run
                    ORDER BY source, started_at DESC, id DESC
                    """
                )
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                return []
            assert cur.description is not None  # always set after a SELECT
            columns = [d.name for d in cur.description]
            return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]
