"""Read-only operational metrics for repeatable database builds.

``mlb metrics`` gives an operator enough evidence to distinguish an
upstream-download problem from a PostgreSQL write or storage problem before
changing a loader. The numbers are snapshots, not a replacement for doctor.
"""

from dataclasses import dataclass

from mlb_baseball.db import fetch_one, get_connection


@dataclass(frozen=True)
class DatabaseMetrics:
    database: str
    database_size: str
    connections: int
    cache_hit_pct: float | None
    commits: int
    rollbacks: int


@dataclass(frozen=True)
class SourceMetrics:
    source: str
    window_minutes: int
    changed_items: int
    loaded_items: int
    unavailable_items: int
    failed_items: int


@dataclass(frozen=True)
class TableMetrics:
    table: str
    rows_estimate: int
    dead_rows_estimate: int
    sequential_scans: int
    index_scans: int
    total_size: str


def collect(
    source: str = "mlb_api", window_minutes: int = 5
) -> tuple[DatabaseMetrics, SourceMetrics, list[TableMetrics]]:
    """Return a compact, read-only PostgreSQL and ingestion snapshot."""
    if not 1 <= window_minutes <= 60:
        raise ValueError("window_minutes must be between 1 and 60")

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT current_database(), pg_size_pretty(pg_database_size(current_database())),
                   numbackends, xact_commit, xact_rollback,
                   round(100.0 * blks_hit / NULLIF(blks_hit + blks_read, 0), 2)
            FROM pg_stat_database
            WHERE datname = current_database()
            """
        )
        database, size, connections, commits, rollbacks, cache_hit = fetch_one(cur)
        database_metrics = DatabaseMetrics(
            database=database,
            database_size=size,
            connections=connections,
            cache_hit_pct=float(cache_hit) if cache_hit is not None else None,
            commits=commits,
            rollbacks=rollbacks,
        )

        cur.execute(
            """
            SELECT count(*),
                   count(*) FILTER (WHERE status = 'loaded'),
                   count(*) FILTER (WHERE status = 'unavailable'),
                   count(*) FILTER (WHERE status = 'failed')
            FROM meta.ingestion_item
            WHERE source = %s
              AND updated_at >= now() - make_interval(mins => %s)
            """,
            (source, window_minutes),
        )
        changed, loaded, unavailable, failed = fetch_one(cur)
        source_metrics = SourceMetrics(
            source=source,
            window_minutes=window_minutes,
            changed_items=changed,
            loaded_items=loaded,
            unavailable_items=unavailable,
            failed_items=failed,
        )

        cur.execute(
            """
            SELECT relname, n_live_tup, n_dead_tup, seq_scan, idx_scan,
                   pg_size_pretty(pg_total_relation_size(relid))
            FROM pg_stat_user_tables
            WHERE schemaname = 'raw'
              AND relname IN ('mlb_win_prob', 'mlb_game_context', 'mlb_linescore')
            ORDER BY relname
            """
        )
        tables = [
            TableMetrics(
                table=row[0],
                rows_estimate=row[1],
                dead_rows_estimate=row[2],
                sequential_scans=row[3],
                index_scans=row[4],
                total_size=row[5],
            )
            for row in cur.fetchall()
        ]
    return database_metrics, source_metrics, tables


def print_report(source: str = "mlb_api", window_minutes: int = 5) -> None:
    """Print a human-readable snapshot suitable for a build log."""
    database, ingestion, tables = collect(source, window_minutes)
    cache = "n/a" if database.cache_hit_pct is None else f"{database.cache_hit_pct:.1f}%"
    print(
        f"database={database.database} size={database.database_size} "
        f"connections={database.connections} cache_hit={cache} "
        f"commits={database.commits} rollbacks={database.rollbacks}"
    )
    print(
        f"{ingestion.source} last_{ingestion.window_minutes}m: "
        f"changed={ingestion.changed_items} loaded={ingestion.loaded_items} "
        f"unavailable={ingestion.unavailable_items} failed={ingestion.failed_items}"
    )
    for table in tables:
        print(
            f"raw.{table.table}: rows≈{table.rows_estimate} dead≈{table.dead_rows_estimate} "
            f"seq_scans={table.sequential_scans} index_scans={table.index_scans} "
            f"size={table.total_size}"
        )
