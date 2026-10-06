"""Live inventory of what's actually in the database: every raw/core/gold
table with its row count, plus the last ingestion run per source. Deliberately
not a static doc snapshot — with connectors landing dozens of tables now, a
written inventory would go stale the moment ingestion runs again. This
queries current state every time, so it's always right.
"""

import json

import psycopg

from mlb_baseball.db import fetch_one, get_connection


def tables(*, partitions: bool = True, exact: bool = True) -> list[dict]:
    """Return live relation inventory.

    The public function preserves the original exact, every-relation behavior.
    The CLI opts into the faster parent-only estimate mode, which keeps a
    normal bootstrap status check readable even with hundreds of empty yearly
    ``core.play`` and ``core.pitch`` partitions.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            child_filter = (
                ""
                if partitions
                else "AND NOT EXISTS (SELECT 1 FROM pg_inherits i WHERE i.inhrelid = c.oid)"
            )
            if exact:
                relation_kind = "c.relkind IN ('r', 'p')"
                cur.execute(
                    f"""
                    SELECT n.nspname, c.relname
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname IN ('raw', 'core', 'gold') AND {relation_kind}
                    {child_filter}
                    ORDER BY 1, 2
                    """
                )
            else:
                cur.execute(
                    f"""
                    SELECT n.nspname, c.relname,
                           CASE WHEN c.relkind = 'p' THEN coalesce((
                               SELECT sum(
                                   coalesce(child_stats.n_live_tup, child.reltuples::bigint, 0)
                               )
                               FROM pg_inherits inheritance
                               JOIN pg_class child ON child.oid = inheritance.inhrelid
                               LEFT JOIN pg_stat_all_tables child_stats
                                 ON child_stats.relid = child.oid
                               WHERE inheritance.inhparent = c.oid
                           ), 0)
                           ELSE coalesce(s.n_live_tup, c.reltuples::bigint, 0) END
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    LEFT JOIN pg_stat_all_tables s ON s.relid = c.oid
                    WHERE n.nspname IN ('raw', 'core', 'gold')
                      AND c.relkind IN ('r', 'p')
                    {child_filter}
                    ORDER BY 1, 2
                    """
                )
            schema_tables = cur.fetchall()

        result = []
        if not exact:
            return [
                {"schema": schema, "table": table, "rows": row_count, "exact": False}
                for schema, table, row_count in schema_tables
            ]
        with conn.cursor() as cur:
            for schema, table in schema_tables:
                cur.execute(f"SELECT count(*) FROM {schema}.{table}")
                (row_count,) = fetch_one(cur)
                result.append({"schema": schema, "table": table, "rows": row_count, "exact": True})
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


def save_profile() -> int:
    """Recompute ``meta.raw_profile`` (the only write here); returns tables profiled."""
    from mlb_baseball.coverage.registry import DATE_COLUMNS

    declared = {table.removeprefix("raw."): column for table, column in DATE_COLUMNS.items()}
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT meta.refresh_raw_profile(NULL, %s::jsonb)", (json.dumps(declared),))
        (written,) = fetch_one(cur)
        conn.commit()
    return int(written)


def _source_of(table: str) -> str:
    """Source group = the table-name prefix before the first underscore."""
    return table.split("_", 1)[0]


def raw_markdown() -> str:
    """Render the raw layer as markdown: exact rows, season range and columns.

    Season range uses the ``_season`` column when a table has one (the raw
    connectors scope loads by it); tables without it show ``-``. All reads are
    plain SELECTs, so the report is as current as the database it ran against.
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(
            """
            SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod)
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
            WHERE n.nspname = 'raw' AND c.relkind IN ('r', 'p')
              AND NOT EXISTS (SELECT 1 FROM pg_inherits i WHERE i.inhrelid = c.oid)
            ORDER BY c.relname, a.attnum
            """
        )
        columns: dict[str, list[tuple[str, str]]] = {}
        for table, column, data_type in cur.fetchall():
            columns.setdefault(table, []).append((column, data_type))
        stats: dict[str, tuple[int, str]] = {}
        for table, cols in columns.items():
            cur.execute(f"SELECT count(*) FROM raw.{table}")
            (rows,) = fetch_one(cur)
            seasons = "-"
            if rows and any(name == "_season" for name, _ in cols):
                cur.execute(f"SELECT min(_season), max(_season) FROM raw.{table}")
                low, high = fetch_one(cur)
                if low is not None:
                    seasons = f"{low}-{high}"
            stats[table] = (rows, seasons)

    out = [
        "# Raw layer inventory (generated)",
        "",
        "Generated by `mlb inventory --markdown`; exact row counts from the database it was run "
        "against. Do not edit by hand: re-run the command. What each source offers versus what "
        "is stored lives in `docs/SOURCE_COVERAGE_AUDIT.md`.",
        "",
    ]
    by_source: dict[str, list[str]] = {}
    for table in columns:
        by_source.setdefault(_source_of(table), []).append(table)
    for source in sorted(by_source):
        out += [f"## {source}", "", "| table | rows | seasons | columns |", "|---|---:|---|---:|"]
        for table in sorted(by_source[source]):
            rows, seasons = stats[table]
            out.append(f"| `raw.{table}` | {rows} | {seasons} | {len(columns[table])} |")
        out.append("")
        for table in sorted(by_source[source]):
            out += [f"<details><summary><code>raw.{table}</code> columns</summary>", ""]
            out += [f"- `{name}` {data_type}" for name, data_type in columns[table]]
            out += ["", "</details>", ""]
    return "\n".join(out)
