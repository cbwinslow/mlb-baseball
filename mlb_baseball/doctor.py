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

from mlb_baseball import conform, ingest, manifest, migrate, model, report
from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check
from mlb_baseball.model import experiment
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


_REQUIRED_SCHEMAS = {"raw", "core", "gold", "meta"}


def _required_schemas_exist() -> Check:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT nspname FROM pg_namespace WHERE nspname = ANY(%s)",
                (list(_REQUIRED_SCHEMAS),),
            )
            found = {row[0] for row in cur.fetchall()}
    missing = _REQUIRED_SCHEMAS - found
    if missing:
        return Check(
            "required schemas",
            False,
            f"missing: {', '.join(sorted(missing))} — run `mlb migrate`",
        )
    return Check("required schemas", True, f"{', '.join(sorted(_REQUIRED_SCHEMAS))} all present")


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


def _pg_stat_statements_enabled() -> Check:
    """Confirms pg_stat_statements is actually installed and tracking, not
    just present in pg_available_extensions — it requires being loaded via
    shared_preload_libraries (a server restart, not a plain CREATE
    EXTENSION), so a `CREATE EXTENSION IF NOT EXISTS` here could silently
    "succeed" while the extension still isn't actually recording anything.
    This is what makes real query-timing investigations possible at all
    (see docs/DECISIONS.md ADR-043) — flagging it here means a missing
    monitoring precondition shows up in `mlb doctor`, not only when someone
    goes looking for it mid-investigation."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements'")
            if cur.fetchone() is None:
                return Check(
                    "pg_stat_statements",
                    False,
                    "not installed — run `CREATE EXTENSION pg_stat_statements` "
                    "(requires it in shared_preload_libraries first, server restart needed)",
                )
            cur.execute("SELECT count(*) FROM pg_stat_statements")
            (count,) = fetch_one(cur)
    return Check("pg_stat_statements", True, f"tracking {count} distinct statements")


def _stale_ingestion_runs() -> Check:
    """Report stale runs without changing operational state.

    ``mlb doctor`` is deliberately safe to run in monitoring and CI.  An
    owner can explicitly repair these rows with ``mlb repair-runs``.
    """
    with get_connection() as conn:
        try:
            stale = ingest.stale_runs(conn)
        except psycopg.errors.UndefinedTable:
            conn.rollback()
            return Check(
                "stale ingestion runs",
                True,
                "meta.ingestion_run doesn't exist yet — nothing to check",
            )
    if not stale:
        return Check("stale ingestion runs", True, "none found")
    names = ", ".join(f"{r['source']} ({r['mode']}, pid {r['pid']})" for r in stale)
    return Check(
        "stale ingestion runs", False, f"{len(stale)} found: {names} — run `mlb repair-runs`"
    )


def _workflow_lock_state() -> Check:
    """Expose a live workflow conflict without changing its owner or state."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.pid, a.state
            FROM pg_locks l
            JOIN pg_stat_activity a ON a.pid = l.pid
            WHERE l.locktype = 'advisory'
              AND l.objid = hashtext('mlb-workflow:raw-core-model')::oid
              AND l.granted AND a.pid <> pg_backend_pid()
            ORDER BY a.pid
            """
        )
        holders = cur.fetchall()
    if not holders:
        return Check("workflow lock", True, "no active raw/core/model workflow")
    details = ", ".join(f"pid {pid} ({state})" for pid, state in holders)
    return Check(
        "workflow lock",
        False,
        f"active workflow lock held by {details} — wait for it to finish; "
        "do not start ingest/conform/model",
    )


# (name, check_fn) — every entry runs independently and defensively: a bug or
# an unexpected DB state in any one check must never prevent the rest from
# reporting, since that's exactly the "doctor itself is broken" failure mode
# this command exists to avoid for every *other* part of the system.
_CORE_CHECKS = [
    ("required schemas", _required_schemas_exist),
    ("migrations", _migrations_up_to_date),
    ("downloads directory", _downloads_directory_ok),
    ("pg_stat_statements", _pg_stat_statements_enabled),
    ("stale ingestion runs", _stale_ingestion_runs),
    ("workflow lock", _workflow_lock_state),
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

    # conform.py isn't in CONNECTORS — it has no bootstrap()/update() (it
    # transforms already-ingested raw data rather than fetching from a
    # source), so it's checked here directly instead of through the
    # connector loop above.
    try:
        checks.extend(conform.health_check())
    except Exception as exc:
        checks.append(Check("core connector", False, f"health_check() raised: {exc}"))

    # Same reasoning as conform.py above -- model has no bootstrap()/
    # update(), it's not in CONNECTORS.
    try:
        checks.extend(model.health_check())
    except Exception as exc:
        checks.append(Check("model", False, f"health_check() raised: {exc}"))

    # Reporting is a separate derived stage, like conformance and model
    # building rather than a network connector.  It must be visible in the
    # one-command operational picture too.
    try:
        checks.extend(report.health_check())
    except Exception as exc:
        checks.append(Check("report", False, f"health_check() raised: {exc}"))

    try:
        checks.extend(experiment.health_check())
    except Exception as exc:
        checks.append(Check("experiment", False, f"health_check() raised: {exc}"))

    return checks
