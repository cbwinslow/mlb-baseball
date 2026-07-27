"""Shared primitives for `mlb doctor` — see CLAUDE.md "Operational health checks".
Deliberately has no dependency on connectors or the registry, so connector
modules can import from here without creating an import cycle.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import psycopg

from mlb_baseball.db import get_connection


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def check_table_has_rows(table: str) -> Check:
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(f"SELECT count(*) FROM {table}")
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                return Check(table, False, "table does not exist — never bootstrapped?")
            (count,) = cur.fetchone()
    if count == 0:
        return Check(table, False, "0 rows — never ingested?")
    return Check(table, True, f"{count} rows")


def check_table_exists(table: str) -> Check:
    """Like check_table_has_rows, but doesn't require any rows — for genuinely
    sparse/event-driven tables where 0 rows is a valid healthy state (e.g.
    raw.mlb_live_game outside of live-game hours: nothing wrong, there's just
    nothing live to capture right now)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(f"SELECT count(*) FROM {table}")
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                return Check(table, False, "table does not exist — never bootstrapped?")
            (count,) = cur.fetchone()
    return Check(table, True, f"{count} rows")


def check_last_run(source: str) -> Check:
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "SELECT status, started_at FROM meta.ingestion_run "
                    "WHERE source = %s ORDER BY id DESC LIMIT 1",
                    (source,),
                )
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                return Check(
                    f"{source} last run",
                    False,
                    "meta.ingestion_run does not exist — run `mlb migrate`",
                )
            row = cur.fetchone()
    if row is None:
        return Check(f"{source} last run", False, "never run")
    status, started_at = row
    return Check(f"{source} last run", status == "success", f"{status} at {started_at}")


def check_recent_run(source: str, max_age_minutes: int) -> Check:
    """For sources expected to run on a repeating schedule (e.g. mlb_api's
    cron-driven live-game capture) — check_last_run only tells you whether
    the *last* run succeeded, not whether the scheduler is still running at
    all. A cron job that silently stopped (crashed host, disabled crontab
    entry, expired credentials) still has an old "success" row forever,
    which check_last_run alone would report as healthy indefinitely."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "SELECT status, started_at FROM meta.ingestion_run "
                    "WHERE source = %s ORDER BY id DESC LIMIT 1",
                    (source,),
                )
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                return Check(
                    f"{source} freshness",
                    False,
                    "meta.ingestion_run does not exist — run `mlb migrate`",
                )
            row = cur.fetchone()
    if row is None:
        return Check(f"{source} freshness", False, "never run")
    status, started_at = row
    if status != "success":
        return Check(f"{source} freshness", False, f"last run {status}, not success")
    age = datetime.now(UTC) - started_at
    if age > timedelta(minutes=max_age_minutes):
        return Check(
            f"{source} freshness",
            False,
            f"last successful run was {age} ago (older than {max_age_minutes}m) — "
            "is the scheduled job still running? check `crontab -l`",
        )
    return Check(f"{source} freshness", True, f"last run {age} ago")
