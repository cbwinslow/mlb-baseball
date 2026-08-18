from pathlib import Path

import psycopg

from mlb_baseball.db import fetch_one, get_connection

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
        if not fetch_one(cur)[0]:
            raise RuntimeError("migration: another migration run is already active")


def _release_migration_lock(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_unlock(hashtext('mlb-migrate'))")


def _strip_sql_comments(sql: str) -> str:
    """Removes `-- ...` comments (to end of line) before splitting on `;` --
    a semicolon inside a comment must not be treated as a statement
    delimiter. Found the hard way: migration 0038's own explanatory
    comments contained a semicolon in a plain English sentence, which the
    old naive `sql.split(";")` treated as a statement boundary, producing
    a confusing "syntax error near <fragment of comment prose>" with no
    hint that the real cause was comment-unaware splitting. Deliberately
    simple (no string-literal awareness) since this project's migrations
    are plain DDL that never puts `--` inside a string value."""
    lines = []
    for line in sql.splitlines():
        comment_start = line.find("--")
        lines.append(line[:comment_start] if comment_start != -1 else line)
    return "\n".join(lines)


def _apply_nontransactional_migration(conn: psycopg.Connection, sql: str) -> None:
    """Run an explicitly marked operational migration one statement at a time.

    PostgreSQL prohibits ``CREATE INDEX CONCURRENTLY`` inside a transaction.
    This narrow escape hatch is intentionally opt-in, rejects normal migration
    files, and leaves the ledger row absent until every idempotent statement
    succeeds, making a retry the recovery path after interruption.
    """
    stripped = _strip_sql_comments(sql)
    statements = [statement.strip() for statement in stripped.split(";") if statement.strip()]
    old_autocommit = conn.autocommit
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)
    finally:
        conn.autocommit = old_autocommit


def run(skip: set[str] | None = None) -> list[str]:
    """Apply every pending migration in filename order.

    ``skip`` defers specific versions to a later run -- for a rare, documented
    forward dependency where an earlier migration's own precondition (e.g. no
    duplicate keys) can only be satisfied by data work that a *later*
    migration's schema change unblocks (see 0040/0045, ADR: production
    game_pk dedup). Skipped versions are never marked applied; a later
    unskipped run still requires and applies them in order.
    """
    skip = skip or set()
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
                if version in already_applied or version in skip:
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
        except Exception:
            # A failed migration leaves psycopg's transaction aborted. Roll
            # back before releasing the session advisory lock so a useful
            # original error is returned and a retry can acquire the lock.
            conn.rollback()
            raise
        finally:
            _release_migration_lock(conn)
    return applied


def main(skip: set[str] | None = None) -> None:
    applied = run(skip=skip)
    if not applied:
        print("No pending migrations.")
    else:
        for version in applied:
            print(f"Applied {version}")


if __name__ == "__main__":
    main()
