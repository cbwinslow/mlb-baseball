import sys
from pathlib import Path

import psycopg

from mlb_baseball.db import get_connection

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


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


def run() -> list[str]:
    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    applied = []
    with get_connection() as conn:
        _ensure_tracking_table(conn)
        already_applied = _applied_versions(conn)
        for path in migration_files:
            version = path.name
            if version in already_applied:
                continue
            sql = path.read_text()
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO public.schema_migrations (version) VALUES (%s)",
                    (version,),
                )
            conn.commit()
            applied.append(version)
    return applied


def main() -> None:
    applied = run()
    if not applied:
        print("No pending migrations.")
    else:
        for version in applied:
            print(f"Applied {version}")


if __name__ == "__main__":
    sys.exit(main())
