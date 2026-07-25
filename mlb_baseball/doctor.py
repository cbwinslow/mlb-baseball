"""`mlb doctor` — one command to check whether everything is actually working.
See CLAUDE.md "Operational health checks": every connector is expected to
contribute its own checks via health_check(), not be invisible until it
breaks.

Every check here is defensive against a database that's reachable but
otherwise not yet set up (no schemas, no migrations applied) — that's not a
hypothetical: it's exactly the state a brand-new clone's database is in
before the first `mlb migrate`, and doctor crashing with a raw traceback
right there is the worst possible first impression. Detail messages name the
actual next command to run (`mlb migrate`, `mlb ingest <source> --mode
bootstrap`) wherever there's an obvious one, not just "X is wrong" — the
point is to make doctor's output something a person (or an agent) can act on
directly, not just a status light.
"""

import psycopg

from mlb_baseball import manifest, migrate
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
        return Check(
            "database reachable",
            False,
            f"{exc} — check DATABASE_URL in .env points at a running Postgres instance",
        )


def _required_schemas_exist() -> Check:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT nspname FROM pg_namespace WHERE nspname IN ('raw', 'conformed', 'meta')"
            )
            found = {row[0] for row in cur.fetchall()}
    missing = {"raw", "conformed", "meta"} - found
    if missing:
        return Check(
            "required schemas",
            False,
            f"missing: {', '.join(sorted(missing))} — run `mlb migrate`",
        )
    return Check("required schemas", True, "raw, conformed, meta all present")


def _migrations_up_to_date() -> Check:
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT version FROM public.schema_migrations")
            except psycopg.errors.UndefinedTable:
                conn.rollback()
                return Check("migrations", False, "no migrations applied yet — run `mlb migrate`")
            applied = {row[0] for row in cur.fetchall()}
    all_migrations = {p.name for p in migrate.MIGRATIONS_DIR.glob("*.sql")}
    pending = all_migrations - applied
    if pending:
        return Check(
            "migrations",
            False,
            f"pending: {', '.join(sorted(pending))} — run `mlb migrate`",
        )
    return Check("migrations", True, f"{len(applied)} applied, none pending")


def _downloads_directory_ok() -> Check:
    ok, detail = manifest.check_downloads_directory()
    return Check("downloads directory", ok, detail)


# (name, check_fn) — every entry runs independently and defensively: a bug or
# an unexpected DB state in any one check must never prevent the rest from
# reporting, since that's exactly the "doctor itself is broken" failure mode
# this command exists to avoid for every *other* part of the system.
_CORE_CHECKS = [
    ("required schemas", _required_schemas_exist),
    ("migrations", _migrations_up_to_date),
    ("downloads directory", _downloads_directory_ok),
]


def run() -> list[Check]:
    db_check = _database_reachable()
    if not db_check.ok:
        return [db_check]  # nothing else can run without a DB connection

    checks = [db_check]
    for name, check_fn in _CORE_CHECKS:
        try:
            checks.append(check_fn())
        except Exception as exc:
            checks.append(Check(name, False, f"check raised: {exc}"))

    for name, connector in CONNECTORS.items():
        health_check = getattr(connector, "health_check", None)
        if health_check is None:
            checks.append(Check(f"{name} connector", False, "no health_check() defined"))
            continue
        try:
            checks.extend(health_check())
        except Exception as exc:
            # One connector's health_check() blowing up (e.g. querying a table
            # that's never been bootstrapped) shouldn't blind doctor to every
            # other connector's health — report it as a failed check instead.
            checks.append(Check(f"{name} connector", False, f"health_check() raised: {exc}"))

    return checks
