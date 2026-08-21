"""Drops per-run test databases (tests/conftest.py's postgresql_noproc
fixture, mlb_test_<hex>) left behind by a pytest process that crashed
before its own teardown ran. See
docs/superpowers/plans/2026-08-21-test-db-isolation.md Task 5.

Never touches `mlb`, or any database not matching the mlb_test_<hex>
naming pattern this project's test suite uses -- see CLAUDE.md's database
golden rule.
"""

import time

import psycopg

_PATTERN = "mlb\\_test\\_%"  # escaped for LIKE: literal underscores, not wildcards


def find_orphaned_test_databases(cur: psycopg.Cursor) -> list[str]:
    """Database names matching the per-run test naming pattern with zero
    currently active connections -- see module docstring for why zero
    connections is a sufficient, not just necessary, signal here."""
    cur.execute(
        """
        SELECT d.datname
        FROM pg_database d
        WHERE d.datname LIKE %s
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
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            first_pass = set(find_orphaned_test_databases(cur))
        if not first_pass:
            return []

        time.sleep(recheck_delay_seconds)

        with conn.cursor() as cur:
            second_pass = set(find_orphaned_test_databases(cur))

        still_orphaned = sorted(first_pass & second_pass)
        with conn.cursor() as cur:
            for dbname in still_orphaned:
                cur.execute(f'DROP DATABASE IF EXISTS "{dbname}"')
    return still_orphaned
