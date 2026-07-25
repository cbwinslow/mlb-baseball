"""Live inventory of what's actually in the database: every raw/conformed table
with its row count, plus the last ingestion run per source. Deliberately not a
static doc snapshot — with connectors landing dozens of tables now, a written
inventory would go stale the moment ingestion runs again. This queries current
state every time, so it's always right.
"""

from mlb_baseball.db import get_connection


def tables() -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT n.nspname, c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname IN ('raw', 'conformed') AND c.relkind = 'r'
                ORDER BY 1, 2
                """
            )
            schema_tables = cur.fetchall()

        result = []
        with conn.cursor() as cur:
            for schema, table in schema_tables:
                cur.execute(f"SELECT count(*) FROM {schema}.{table}")
                (row_count,) = cur.fetchone()
                result.append({"schema": schema, "table": table, "rows": row_count})
        return result


def last_runs() -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (source)
                    source, mode, status, rows, started_at, finished_at
                FROM meta.ingestion_run
                ORDER BY source, started_at DESC, id DESC
                """
            )
            columns = [d.name for d in cur.description]
            return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]
