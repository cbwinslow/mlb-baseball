"""Shared run-tracking for connectors. See docs/ARCHITECTURE.md "Connector contract"."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

import psycopg

from mlb_baseball.db import fetch_one


def record_items(conn: psycopg.Connection, items: list[dict]) -> None:
    """Atomically upsert completed source items after their raw rows land.

    The caller supplies one immutable source item (for example,
    ``analytics_win_probability`` / ``1967:153395``) per dict. ``loaded``
    may be retried safely; ``unavailable`` records a permanent source 404 so
    a resume does not waste another request on it.
    """
    if not items:
        return
    required = {"source", "dataset", "item_key", "status"}
    if any(required - item.keys() for item in items):
        raise ValueError(f"ingestion item missing required keys: {sorted(required)}")
    columns = [
        "source",
        "dataset",
        "item_key",
        "status",
        "source_url",
        "artifact_path",
        "artifact_sha256",
        "bytes",
        "http_status",
        "rows",
        "parser_version",
        "schema_fingerprint",
        "error",
        "run_id",
    ]
    values = [tuple(item.get(column) for column in columns) for item in items]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO meta.ingestion_item (
                source, dataset, item_key, status, source_url, artifact_path,
                artifact_sha256, bytes, http_status, rows, parser_version,
                schema_fingerprint, error, run_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source, dataset, item_key) DO UPDATE SET
                status = EXCLUDED.status,
                attempts = meta.ingestion_item.attempts + 1,
                source_url = EXCLUDED.source_url,
                artifact_path = EXCLUDED.artifact_path,
                artifact_sha256 = EXCLUDED.artifact_sha256,
                bytes = EXCLUDED.bytes,
                http_status = EXCLUDED.http_status,
                rows = EXCLUDED.rows,
                parser_version = EXCLUDED.parser_version,
                schema_fingerprint = EXCLUDED.schema_fingerprint,
                error = EXCLUDED.error,
                run_id = EXCLUDED.run_id,
                retrieved_at = now(),
                updated_at = now()
            """,
            values,
        )


def _acquire_source_lock(conn: psycopg.Connection, source: str) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (f"mlb-ingest:{source}",))
        if not fetch_one(cur)[0]:
            raise RuntimeError(f"{source}: another ingestion run is already active")


def _release_source_lock(conn: psycopg.Connection, source: str) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_unlock(hashtext(%s))", (f"mlb-ingest:{source}",))


def _acquire_workflow_lock(
    conn: psycopg.Connection, workflow: Literal["shared", "exclusive"]
) -> None:
    """Coordinate raw ingestion with stages that replace derived tables.

    Connectors take a shared lock and may run together.  Conformance and
    feature/prediction workflows take the exclusive form, so they cannot read
    a changing raw layer or overlap each other.  Locks are session-scoped and
    therefore survive the commits used for ingestion-run bookkeeping.
    """
    function = "pg_try_advisory_lock_shared" if workflow == "shared" else "pg_try_advisory_lock"
    with conn.cursor() as cur:
        cur.execute(f"SELECT {function}(hashtext(%s))", ("mlb-workflow:raw-core-model",))
        if not fetch_one(cur)[0]:
            raise RuntimeError("workflow: another ingestion or derived-data stage is active")


def _release_workflow_lock(
    conn: psycopg.Connection, workflow: Literal["shared", "exclusive"]
) -> None:
    function = "pg_advisory_unlock_shared" if workflow == "shared" else "pg_advisory_unlock"
    with conn.cursor() as cur:
        cur.execute(f"SELECT {function}(hashtext(%s))", ("mlb-workflow:raw-core-model",))


@contextmanager
def track_run(
    conn: psycopg.Connection,
    source: str,
    mode: str,
    *,
    workflow: Literal["shared", "exclusive"] = "shared",
) -> Iterator[dict]:
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
    _acquire_source_lock(conn, source)
    try:
        _acquire_workflow_lock(conn, workflow)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO meta.ingestion_run (source, mode, status, pid) "
                "VALUES (%s, %s, 'running', %s) RETURNING id",
                (source, mode, os.getpid()),
            )
            run_id = fetch_one(cur)[0]
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
    finally:
        try:
            _release_workflow_lock(conn, workflow)
        finally:
            _release_source_lock(conn, source)


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


def stale_runs(conn: psycopg.Connection) -> list[dict]:
    """Return dead-process running rows without changing the database."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, source, mode, pid, started_at FROM meta.ingestion_run "
            "WHERE status = 'running' AND pid IS NOT NULL"
        )
        running = cur.fetchall()
    return [
        {"id": run_id, "source": source, "mode": mode, "pid": pid, "started_at": started_at}
        for run_id, source, mode, pid, started_at in running
        if not _pid_is_alive(pid)
    ]


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
    reaped = []
    for run in stale_runs(conn):
        run_id, source, mode, pid, started_at = (
            run["id"],
            run["source"],
            run["mode"],
            run["pid"],
            run["started_at"],
        )
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
