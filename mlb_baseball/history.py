"""When a market's history is complete, and the per-market trade backfill.

A history item (price bars, a price window, a market's trades) is complete only if it
was fetched **after** the thing it describes had ended. Treating "fetched once" as
complete silently kept cut-off histories (openspec/changes/odds-bulk-history, ADR-304).
"""

import logging
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import psycopg

from mlb_baseball.db import get_connection
from mlb_baseball.ingest import record_items, track_run
from mlb_baseball.load import ensure_table
from mlb_baseball.opsmon import Monitor

logger = logging.getLogger(__name__)

# Something that ended less than this long ago may still change: fetch it again later.
SETTLE_SECONDS = 86400


def is_complete(ended_ts: float | None, fetched_ts: float | None, now: float) -> bool:
    """True if the item ended at least a day ago and was fetched after it ended."""
    return (
        ended_ts is not None
        and fetched_ts is not None
        and ended_ts + SETTLE_SECONDS <= now
        and fetched_ts >= ended_ts
    )


def fetched_times(conn: psycopg.Connection, source: str, dataset: str) -> dict[str, float]:
    """``item_key`` -> when it was last fetched successfully (Unix seconds)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT item_key, extract(epoch FROM updated_at)::float8 FROM meta.ingestion_item "
            "WHERE source = %s AND dataset = %s AND status IN ('loaded', 'unavailable')",
            (source, dataset),
        )
        return dict(cur.fetchall())


@dataclass(frozen=True)
class TradeMarket:
    """One market to fetch; ``key`` is the value of the trade table's key column."""

    key: str
    ended_ts: float | None
    context: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TradeDataset:
    source: str  # ledger source
    run_source: str  # run-ledger name: its own, so a long backfill blocks nothing else
    dataset: str
    table: str
    key_column: str
    columns: tuple[str, ...]


class _Writer:
    """One database connection per worker thread; replaces one market per transaction."""

    def __init__(self, spec: TradeDataset) -> None:
        self.spec = spec
        self.local = threading.local()
        self.connections: list[psycopg.Connection] = []
        self.lock = threading.Lock()
        self.columns: set[str] = set(spec.columns)

    def connection(self) -> psycopg.Connection:
        conn = getattr(self.local, "conn", None)
        if conn is None or conn.closed:
            conn = self.local.conn = get_connection()
            with self.lock:
                self.connections.append(conn)
        return conn

    def close(self) -> None:
        for conn in self.connections:
            if not conn.closed:
                conn.close()

    def replace(self, conn: psycopg.Connection, key: str, rows: Sequence[dict]) -> None:
        """Replace one market's rows in the caller's transaction. No rows: keep what is
        stored (a source that stops serving old trades must not erase them)."""
        if not rows:
            return
        columns = list(dict.fromkeys([*self.spec.columns, *(c for row in rows for c in row)]))
        if set(columns) - self.columns:
            with self.lock:
                ensure_table(conn, self.spec.table, columns, index_column=self.spec.key_column)
                conn.commit()
                self.columns.update(columns)
        schema, name = self.spec.table.split(".")
        table = psycopg.sql.Identifier(schema, name)
        with conn.cursor() as cur:
            cur.execute(
                psycopg.sql.SQL("DELETE FROM {} WHERE {} = %s").format(
                    table, psycopg.sql.Identifier(self.spec.key_column)
                ),
                (key,),
            )
            copy_sql = psycopg.sql.SQL("COPY {} ({}) FROM STDIN").format(
                table, psycopg.sql.SQL(", ").join(map(psycopg.sql.Identifier, columns))
            )
            with cur.copy(copy_sql) as copy:
                for row in rows:
                    copy.write_row([_text(row.get(c)) for c in columns])


def _text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def backfill_trades(
    spec: TradeDataset,
    markets: Callable[[psycopg.Connection], list[TradeMarket]],
    fetch: Callable[[TradeMarket], list[dict]],
    *,
    workers: int,
    now: float,
) -> int:
    """Fetch and land the trades of every market that is not complete yet. Each market
    commits together with its ledger row, so a stopped run resumes where it left off.
    Raises at the end if any market failed, after trying all of them."""
    writer = _Writer(spec)
    with (
        get_connection() as conn,
        track_run(conn, spec.run_source, "backfill", workflow=None) as result,
    ):
        run_id = result["run_id"]
        ensure_table(conn, spec.table, list(spec.columns), index_column=spec.key_column)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s",
                tuple(spec.table.split(".")),
            )
            writer.columns.update(name for (name,) in cur.fetchall())
        done = fetched_times(conn, spec.source, spec.dataset)
        todo = [m for m in markets(conn) if not is_complete(m.ended_ts, done.get(m.key), now)]
        conn.commit()
        logger.info("%s: %d markets to fetch", spec.run_source, len(todo))
        monitor = Monitor(run_id=run_id)

        def load(market: TradeMarket) -> tuple[int, int]:
            worker = writer.connection()
            item = {
                "source": spec.source,
                "dataset": spec.dataset,
                "item_key": market.key,
                "run_id": run_id,
            }
            try:
                rows = fetch(market)
                writer.replace(worker, market.key, rows)
                status = "loaded" if rows else "unavailable"
                record_items(worker, [{**item, "status": status, "rows": len(rows)}])
                worker.commit()
                return len(rows), 0
            except Exception as exc:
                worker.rollback()
                logger.error("%s %s failed: %s", spec.run_source, market.key, exc)
                record_items(worker, [{**item, "status": "failed", "error": str(exc)[:500]}])
                worker.commit()
                return 0, 1

        total = failed = finished = 0
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(load, market) for market in todo]
                try:
                    for future in as_completed(futures):
                        rows, bad = future.result()
                        total, failed, finished = total + rows, failed + bad, finished + 1
                        monitor.progress(done=finished, planned=len(todo), requests=finished)
                except BaseException:
                    for future in futures:
                        future.cancel()
                    raise
        finally:
            monitor.finish()
            monitor.close()
            writer.close()
        result["rows"] = total
        if failed:
            raise RuntimeError(
                f"{failed} {spec.run_source} markets failed (recorded as failed in "
                "meta.ingestion_item); rerun to retry them"
            )
    return total
