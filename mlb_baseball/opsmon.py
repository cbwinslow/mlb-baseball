"""Run monitor: time operations and report progress for long jobs.

Thin client for the database objects created by migration 0111
(``meta.op_span``, ``meta.record_op``, ``meta.run_progress``). It writes through
its **own autocommit connection**, so the record survives a rollback of the job's
data transaction, and a monitor failure is logged and swallowed -- telemetry
must never fail the pipeline (same rule as ``nightly.snapshot_query_stats``).

    with track_run(conn, "polymarket", "backfill") as result:
        mon = Monitor(run_id=result["run_id"])
        for batch in batches:
            with mon.timed("polymarket.batch", tokens=len(batch)) as op:
                op.rows = load(batch)
                op.requests = 1
            mon.progress(done=n, planned=total, requests=reqs)
        mon.finish()
        mon.close()
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

import psycopg

from mlb_baseball.db import get_connection

logger = logging.getLogger(__name__)

DEFAULT_PROGRESS_INTERVAL_SECONDS = 30.0


@dataclass
class OpResult:
    """Set ``rows`` / ``requests`` inside a ``timed`` block to record them."""

    rows: int | None = None
    requests: int | None = None


class Monitor:
    def __init__(
        self, run_id: int | None = None, *, min_interval: float = DEFAULT_PROGRESS_INTERVAL_SECONDS
    ) -> None:
        self.run_id = run_id
        self.min_interval = min_interval
        self._conn: psycopg.Connection | None = None
        self._last_write = 0.0
        self._started = time.monotonic()
        self._pending: tuple[int, int | None, int | None] | None = None

    # -- plumbing ---------------------------------------------------------

    def _connection(self) -> psycopg.Connection:
        if self._conn is None or self._conn.closed:
            self._conn = get_connection()
            self._conn.autocommit = True
        return self._conn

    def _execute(self, sql: str, params: tuple) -> None:
        with self._connection().cursor() as cur:
            cur.execute(sql, params)

    def _safely(self, sql: str, params: tuple) -> None:
        try:
            self._execute(sql, params)
        except Exception as exc:
            logger.error("run monitor could not record (%s)", exc)

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
        self._conn = None

    # -- timing -----------------------------------------------------------

    @contextmanager
    def timed(self, op: str, **attrs: object) -> Iterator[OpResult]:
        """Time the block and record one ``meta.op_span`` row (status ``ok``, or
        ``failed`` with the error text if the block raises; the error is re-raised)."""
        result = OpResult()
        started_at = datetime.now(UTC)
        t0 = time.perf_counter()
        status, error = "ok", None
        try:
            yield result
        except BaseException as exc:
            status, error = "failed", f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self._safely(
                "SELECT meta.record_op(%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)",
                (
                    op,
                    started_at,
                    round((time.perf_counter() - t0) * 1000),
                    status,
                    result.rows,
                    result.requests,
                    json.dumps(attrs, default=str),
                    error,
                    self.run_id,
                ),
            )

    # -- progress ---------------------------------------------------------

    def progress(self, done: int, planned: int | None = None, requests: int | None = None) -> None:
        """Report how far the run is. Writes at most once per ``min_interval``
        seconds (the latest state is kept for ``finish``) and logs the rate and
        estimated finish each time it writes."""
        if self.run_id is None:
            return
        self._pending = (done, planned, requests)
        now = time.monotonic()
        if self._last_write and now - self._last_write < self.min_interval:
            return
        self._flush()

    def finish(self) -> None:
        """Write the last reported state regardless of the throttle."""
        if self._pending is not None:
            self._flush(force=True)

    def _flush(self, *, force: bool = False) -> None:
        if self._pending is None or self.run_id is None:
            return
        done, planned, requests = self._pending
        self._pending = None
        self._last_write = time.monotonic()
        self._safely(
            "SELECT meta.run_progress(%s, %s, %s, %s, make_interval(secs => %s))",
            (self.run_id, done, planned, requests, 0 if force else self.min_interval),
        )
        elapsed = max(time.monotonic() - self._started, 1e-9)
        rate = done / elapsed
        if planned and rate > 0:
            remaining = max(planned - done, 0) / rate
            logger.info(
                "run %s: %d/%d items, %.1f/s, about %d min left",
                self.run_id,
                done,
                planned,
                rate,
                round(remaining / 60),
            )
        else:
            logger.info("run %s: %d items, %.1f/s", self.run_id, done, rate)
