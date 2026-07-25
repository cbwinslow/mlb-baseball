"""`mlb doctor` — one command to check whether everything is actually working.
See CLAUDE.md "Operational health checks": every connector is expected to
contribute its own checks via health_check(), not be invisible until it
breaks.
"""

from mlb_baseball import migrate
from mlb_baseball.db import get_connection
from mlb_baseball.health import Check
from mlb_baseball.registry import CONNECTORS


def _database_reachable() -> Check:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return Check("database reachable", True, "connected via DATABASE_URL")
    except Exception as exc:
        return Check("database reachable", False, str(exc))


def _required_schemas_exist() -> Check:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT nspname FROM pg_namespace WHERE nspname IN ('raw', 'conformed', 'meta')"
            )
            found = {row[0] for row in cur.fetchall()}
    missing = {"raw", "conformed", "meta"} - found
    if missing:
        return Check("required schemas", False, f"missing: {', '.join(sorted(missing))}")
    return Check("required schemas", True, "raw, conformed, meta all present")


def _migrations_up_to_date() -> Check:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT version FROM public.schema_migrations")
            applied = {row[0] for row in cur.fetchall()}
    all_migrations = {p.name for p in migrate.MIGRATIONS_DIR.glob("*.sql")}
    pending = all_migrations - applied
    if pending:
        return Check("migrations", False, f"pending: {', '.join(sorted(pending))}")
    return Check("migrations", True, f"{len(applied)} applied, none pending")


def run() -> list[Check]:
    db_check = _database_reachable()
    if not db_check.ok:
        return [db_check]  # nothing else can run without a DB connection

    checks = [db_check, _required_schemas_exist(), _migrations_up_to_date()]

    for name, connector in CONNECTORS.items():
        health_check = getattr(connector, "health_check", None)
        if health_check is None:
            checks.append(Check(f"{name} connector", False, "no health_check() defined"))
        else:
            checks.extend(health_check())

    return checks
