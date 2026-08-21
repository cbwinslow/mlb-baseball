"""Database backup/restore via PostgreSQL's own `pg_dump`/`psql` -- the
tools every real Postgres deployment already trusts for this, not a
reimplemented dump format. Mirrors `chadwick_tools.py`'s external-tool
pattern exactly: `shutil.which()` for presence, `subprocess.run()` with
clear `FileNotFoundError`/non-zero-exit handling, and a `missing_tools()`
hook `mlb doctor` can surface.

`backup()` defaults to a full data+schema dump in `pg_dump`'s plain-SQL
format (`-f` with no `-F`, i.e. `-Fp`): human-readable, diffable, and
restorable by any `psql` regardless of the exact `pg_dump` build that made
it -- the same format the existing manual `backups/mlb_schema_*.sql`
snapshot already used. `--schema-only` mirrors that manual convention
exactly. An optional `schemas` list scopes the dump to specific schemas
(`pg_dump -n`) -- useful for a narrow, fast backup of just `core`/`gold`
without re-dumping all of `raw`'s bulk history every time.

`restore()` is destructive by construction: it overwrites objects in
whatever database `database_url` points to. It refuses to run without an
explicit `confirm=True` -- the CLI entry point requires an explicit
`--yes` flag and always prints the target database name first, the same
"make the target impossible to misread" posture as
`tests/conftest.py`'s own database-name safety check.

A full backup (not schema-only) records itself in `meta.ingestion_run` via
the same `track_run()` every connector uses, so `mlb doctor` can flag a
stale backup with the existing `check_recent_run` helper instead of a
one-off freshness mechanism -- see `health_check()` below.
`rotate_backups()` is the other half of the automated-cron story
(`scripts/mlb_backup.sh`): deletes old full backups beyond a keep count so
a nightly cron doesn't fill the disk.
"""

import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from mlb_baseball.health import DAILY_FRESHNESS_THRESHOLD_MINUTES, Check, check_recent_run
from mlb_baseball.ingest import track_run

REQUIRED_TOOLS = ("pg_dump", "psql")

# meta.ingestion_run source/mode for a full backup -- see migration
# 0065_ingestion_run_backup_mode.sql. Schema-only/scoped dumps aren't tracked
# under this (see backup() below): the freshness check this powers exists to
# answer "is there a recent full backup to restore from," and a schema-only
# snapshot shouldn't be able to mask a stale one.
SOURCE = "backup"

INSTALL_HINT = (
    "install the PostgreSQL client tools for your OS (e.g. `apt install "
    "postgresql-client` on Debian/Ubuntu, `brew install libpq` on macOS) and "
    "make sure pg_dump/psql are on PATH"
)


def missing_tools() -> list[str]:
    """Which of REQUIRED_TOOLS aren't on PATH, if any -- used by
    health_check() so a missing system dependency shows up in `mlb doctor`
    before a backup/restore is attempted, not as a cryptic
    FileNotFoundError partway through one."""
    return [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]


def dbname(database_url: str) -> str:
    """The database name a connection string points at -- used to print an
    unambiguous confirmation of the restore target before doing anything
    destructive."""
    value = psycopg.conninfo.conninfo_to_dict(database_url).get("dbname")
    return str(value) if value else "<unknown>"


def backup(
    database_url: str,
    output_dir: Path,
    *,
    schema_only: bool = False,
    schemas: list[str] | None = None,
) -> Path:
    """Dump `database_url`'s database to a timestamped `.sql` file under
    `output_dir` (created if it doesn't exist). Read-only against the
    source database. Returns the written file's path.

    `schemas`, if given, scopes the dump to only those schemas (pg_dump
    `-n`) instead of the whole database.

    A full dump (`schema_only=False` AND `schemas` empty) is recorded in
    `meta.ingestion_run` for the `mlb doctor` freshness check -- see the
    module docstring. A schema-only OR schema-scoped dump isn't tracked:
    both are ad-hoc/manual by nature, not a stand-in for "is there a
    recent restorable full backup" -- a `--schema raw` dump can't restore
    the whole database, so it must not be able to satisfy that check
    either.

    Tracking runs *after* `_dump()` completes, not wrapped around it:
    `track_run` commits a 'running' row immediately on entry, and
    `pg_dump` takes its MVCC snapshot at the moment it starts -- wrapping
    the dump in `track_run` would freeze that 'running' row into the dump
    itself (a restored backup would then show its own creation as
    perpetually unfinished, defeating the freshness check the very next
    time `mlb doctor` runs against a fresh restore). Deferring the
    (near-instant) tracking bookkeeping to after the dump also means the
    source/workflow advisory locks `track_run` takes are held for a
    fraction of a second, not for however long a multi-GB `pg_dump`
    takes -- a backup no longer risks delaying a scheduled `conform` run
    (which needs the exclusive workflow lock) for its entire duration.
    Trade-off, stated explicitly rather than hidden: two concurrent
    `mlb backup` invocations are no longer prevented from both running
    `pg_dump` at once (only `scripts/mlb_backup.sh`'s own `flock` still
    prevents overlapping *scheduled* runs) -- acceptable since a manual
    concurrent invocation is rare and merely wasteful, not unsafe.
    """
    if missing_tools():
        raise RuntimeError(f"pg_dump not installed or not on PATH -- {INSTALL_HINT}")
    output_dir.mkdir(parents=True, exist_ok=True)
    db = dbname(database_url)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    # A scoped (schemas=[...]) dump gets its own suffix too, not just
    # schema-only: without one it would carry the exact same filename shape
    # as a true full dump, indistinguishable both to a human looking for
    # "the newest real full backup" and to rotate_backups()'s naming-based
    # pattern match.
    if schema_only:
        suffix = "_schema"
    elif schemas:
        suffix = "_scoped"
    else:
        suffix = ""
    output_path = output_dir / f"{db}{suffix}_{timestamp}.sql"

    args = ["pg_dump", "--no-owner", "--no-privileges", "-f", str(output_path)]
    if schema_only:
        args.append("--schema-only")
    for schema in schemas or []:
        args.extend(["-n", schema])
    args.append(database_url)

    def _dump() -> None:
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode != 0:
            output_path.unlink(missing_ok=True)
            raise RuntimeError(f"pg_dump failed: {result.stderr.strip()}")

    if schema_only or schemas:
        _dump()
    else:
        error: Exception | None = None
        try:
            _dump()
        except Exception as exc:
            error = exc
        with psycopg.connect(database_url) as conn, track_run(conn, SOURCE, SOURCE):
            if error is not None:
                raise error
    return output_path


_FULL_BACKUP_TIMESTAMP = r"\d{8}T\d{6}Z"


def rotate_backups(database_url: str, output_dir: Path, *, keep: int) -> list[Path]:
    """Deletes all but the newest `keep` full backups `backup()` itself
    produced in `output_dir` (matched by its exact naming shape, not just
    the `.sql` extension), so a nightly cron doesn't fill the disk.

    Never touches schema-only dumps or any file backup() didn't create --
    e.g. the one small schema snapshot tracked in git (`backups/
    mlb_schema_20260807.sql`), which predates this naming convention and
    has no timestamp suffix to match against anyway.

    Returns the paths deleted.
    """
    if keep < 1:
        raise ValueError("keep must be >= 1")
    db = dbname(database_url)
    pattern = re.compile(rf"^{re.escape(db)}_{_FULL_BACKUP_TIMESTAMP}\.sql$")
    candidates = sorted(
        (p for p in output_dir.glob("*.sql") if pattern.match(p.name)),
        key=lambda p: p.name,
    )
    to_delete = candidates[:-keep] if len(candidates) > keep else []
    for path in to_delete:
        path.unlink()
    return to_delete


def restore(database_url: str, input_path: Path, *, confirm: bool) -> None:
    """Restore `input_path`'s plain-SQL dump into whatever database
    `database_url` points to. DESTRUCTIVE: recreates/overwrites the
    objects the dump contains. Refuses to run unless `confirm=True` --
    callers (the CLI especially) must make the human explicitly confirm
    the target database first.
    """
    if not confirm:
        raise RuntimeError(
            "restore() requires confirm=True -- this overwrites objects in "
            f"database {dbname(database_url)!r}; confirm the target database first"
        )
    if missing_tools():
        raise RuntimeError(f"psql not installed or not on PATH -- {INSTALL_HINT}")
    if not input_path.exists():
        raise RuntimeError(f"backup file not found: {input_path}")

    result = subprocess.run(
        ["psql", "--set", "ON_ERROR_STOP=1", "-f", str(input_path), database_url],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"restore failed: {result.stderr.strip()}")


def health_check() -> list[Check]:
    missing = missing_tools()
    if missing:
        return [
            Check(
                "backup tools (pg_dump/psql)",
                False,
                f"missing: {', '.join(missing)} -- {INSTALL_HINT}",
            )
        ]
    return [
        Check("backup tools (pg_dump/psql)", True, "pg_dump and psql found on PATH"),
        check_recent_run(SOURCE, DAILY_FRESHNESS_THRESHOLD_MINUTES),
    ]
