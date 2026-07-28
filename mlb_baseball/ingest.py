"""Shared run-tracking for connectors. See docs/ARCHITECTURE.md "Connector contract"."""

import os
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg


@contextmanager
def track_run(conn: psycopg.Connection, source: str, mode: str) -> Iterator[dict]:
    """Records a meta.ingestion_run row for the duration of a connector run.

    Yields a dict the caller should set result["rows"] on before the block exits.
    Commits its own bookkeeping independently of whatever transaction the caller's
    data load uses, so a failed load still leaves a readable failure record.

    Stores this process's PID (see reap_stale_runs below) — a process killed
    externally (SIGTERM/SIGKILL, not a caught Python exception) never reaches
    the except/else blocks here, so without a liveness check the row would
    stay "running" forever. A real bug, found by hand (and cleaned up by hand)
    several times in this project's own development before this fix — see
    docs/DECISIONS.md ADR-022.
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.ingestion_run (source, mode, status, pid) "
            "VALUES (%s, %s, 'running', %s) RETURNING id",
            (source, mode, os.getpid()),
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


def _pid_is_alive(pid: int) -> bool:
    """os.kill(pid, 0) sends no actual signal — it only asks the OS whether
    a process with this PID exists and is ours to signal, raising
    ProcessLookupError if not. Only meaningful on the same host the
    connector ran on, which is this project's actual deployment shape (bare-
    metal Postgres + connectors on one machine, ADR-002) — not a general
    distributed-systems liveness check."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists, just owned by another user — still alive.
        return True
    return True


def reap_stale_runs(conn: psycopg.Connection) -> list[dict]:
    """Finds every meta.ingestion_run row still marked 'running' whose
    recorded PID is no longer alive on this host, and marks each 'failed'
    with an explanatory error — the same terminal state a caught Python
    exception would have produced, had the process not been killed
    externally before it could catch anything itself.

    Rows with pid IS NULL (written before migration 0007 added the column)
    are left alone — there's nothing to check liveness against, and a
    reap based on age alone would risk false-flagging a genuinely
    long-running bootstrap (some of this project's historical backfills
    now legitimately run for days).

    Returns the list of rows reaped (as dicts) for the caller to log/report.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, source, mode, pid, started_at FROM meta.ingestion_run "
            "WHERE status = 'running' AND pid IS NOT NULL"
        )
        running = cur.fetchall()

    reaped = []
    for run_id, source, mode, pid, started_at in running:
        if _pid_is_alive(pid):
            continue
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE meta.ingestion_run "
                "SET status = 'failed', "
                "error = 'stale run: process (pid ' || %s || ') no longer running, "
                "reaped by reap_stale_runs()', "
                "finished_at = now() WHERE id = %s",
                (pid, run_id),
            )
        conn.commit()
        reaped.append(
            {"id": run_id, "source": source, "mode": mode, "pid": pid, "started_at": started_at}
        )
    return reaped
