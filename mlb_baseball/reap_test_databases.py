"""Drops per-run test databases (tests/conftest.py's postgresql_noproc
fixture, mlb_test_<hex>) left behind by a pytest process that crashed
before its own teardown ran. See
docs/archive/superpowers-plans/2026-08-21-test-db-isolation.md Task 5.

Never touches `mlb`, or any database not matching the mlb_test_<hex>
naming pattern this project's test suite uses -- see CLAUDE.md's database
golden rule.
"""

import time

import psycopg
from psycopg import sql

_PATTERN = "^mlb_test_[0-9a-f]{12}$"


def _assert_test_dsn(dsn: str) -> None:
    dbname = str(psycopg.conninfo.conninfo_to_dict(dsn).get("dbname") or "")
    if "test" not in dbname.lower() and dbname.lower() not in ("postgres", "template1"):
        raise RuntimeError(
            f"Refusing to run test database reaper against non-test DSN: dbname={dbname!r}"
        )


def find_orphaned_test_databases(cur: psycopg.Cursor) -> list[str]:
    """Database names matching the per-run test naming pattern with zero
    currently active connections -- see module docstring for why zero
    connections is a sufficient, not just necessary, signal here."""
    cur.execute(
        """
        SELECT d.datname
        FROM pg_database d
        WHERE d.datname ~ %s
          AND NOT EXISTS (
              SELECT 1 FROM pg_stat_activity a WHERE a.datname = d.datname
          )
        ORDER BY d.datname
        """,
        (_PATTERN,),
    )
    return [row[0] for row in cur.fetchall()]


def reap_orphaned_test_databases(dsn: str, *, recheck_delay_seconds: float = 5.0) -> list[str]:
    """Drops databases still orphaned after two checks `recheck_delay_seconds`
    apart -- rules out the narrow race of a database just created by a
    session that hasn't connected to it yet."""
    _assert_test_dsn(dsn)
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            first_pass = set(find_orphaned_test_databases(cur))
        if not first_pass:
            return []

        time.sleep(recheck_delay_seconds)

        with conn.cursor() as cur:
            second_pass = set(find_orphaned_test_databases(cur))

        still_orphaned = sorted(first_pass & second_pass)
        dropped: list[str] = []
        with conn.cursor() as cur:
            for dbname in still_orphaned:
                try:
                    cur.execute(
                        sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(dbname))
                    )
                    dropped.append(dbname)
                except psycopg.errors.ObjectInUse:
                    pass
    return dropped
