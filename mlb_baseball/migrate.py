from pathlib import Path

import psycopg

from mlb_baseball.db import get_connection

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
_NONTRANSACTIONAL_MARKER = "-- mlb:nontransactional"


def _ensure_tracking_table(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS public.schema_migrations (
                version text PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    conn.commit()


def _applied_versions(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT version FROM public.schema_migrations")
        return {row[0] for row in cur.fetchall()}


def _acquire_migration_lock(conn: psycopg.Connection) -> None:
    """Prevent concurrent DDL/migration-ledger writers on one database."""
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(hashtext('mlb-migrate'))")
        if not cur.fetchone()[0]:
            raise RuntimeError("migration: another migration run is already active")


def _release_migration_lock(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_unlock(hashtext('mlb-migrate'))")


def _apply_nontransactional_migration(conn: psycopg.Connection, sql: str) -> None:
    """Run an explicitly marked operational migration one statement at a time.

    PostgreSQL prohibits ``CREATE INDEX CONCURRENTLY`` inside a transaction.
    This narrow escape hatch is intentionally opt-in, rejects normal migration
    files, and leaves the ledger row absent until every idempotent statement
    succeeds, making a retry the recovery path after interruption.
    """
    statements = [statement.strip() for statement in sql.split(";") if statement.strip()]
    old_autocommit = conn.autocommit
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for statement in statements:
                if statement == _NONTRANSACTIONAL_MARKER:
                    continue
                cur.execute(statement)
    finally:
        conn.autocommit = old_autocommit


def run() -> list[str]:
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    applied = []
    with get_connection() as conn:
        _acquire_migration_lock(conn)
        try:
            _ensure_tracking_table(conn)
            already_applied = _applied_versions(conn)
            # _applied_versions() is a SELECT but psycopg starts a transaction
            # for it.  End it before an explicitly nontransactional migration
            # switches the connection to autocommit for concurrent DDL.
            conn.commit()
            for path in migration_files:
                version = path.name
                if version in already_applied:
                    continue
                sql = path.read_text()
                if sql.startswith(_NONTRANSACTIONAL_MARKER):
                    _apply_nontransactional_migration(conn, sql)
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO public.schema_migrations (version) VALUES (%s)",
                            (version,),
                        )
                    conn.commit()
                else:
                    with conn.cursor() as cur:
                        cur.execute(sql)
                        cur.execute(
                            "INSERT INTO public.schema_migrations (version) VALUES (%s)",
                            (version,),
                        )
                    conn.commit()
                applied.append(version)
        finally:
            _release_migration_lock(conn)
    return applied


def main() -> None:
    applied = run()
    if not applied:
        print("No pending migrations.")
    else:
        for version in applied:
            print(f"Applied {version}")


if __name__ == "__main__":
    main()
