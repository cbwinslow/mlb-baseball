"""Shared run-tracking for connectors. See docs/ARCHITECTURE.md "Connector contract"."""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg


@contextmanager
def track_run(conn: psycopg.Connection, source: str, mode: str) -> Iterator[dict]:
    """Records a meta.ingestion_run row for the duration of a connector run.

    Yields a dict the caller should set result["rows"] on before the block exits.
    Commits its own bookkeeping independently of whatever transaction the caller's
    data load uses, so a failed load still leaves a readable failure record.
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.ingestion_run (source, mode, status) "
            "VALUES (%s, %s, 'running') RETURNING id",
            (source, mode),
        )
        run_id = cur.fetchone()[0]
    conn.commit()

    result: dict = {"rows": None}
    try:
        yield result
    except Exception as exc:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE meta.ingestion_run "
                "SET status = 'failed', error = %s, finished_at = now() WHERE id = %s",
                (str(exc), run_id),
            )
        conn.commit()
        raise
    else:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE meta.ingestion_run "
                "SET status = 'success', rows = %s, finished_at = now() WHERE id = %s",
                (result.get("rows"), run_id),
            )
        conn.commit()
