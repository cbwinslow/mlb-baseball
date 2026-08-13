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
"""

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from mlb_baseball.health import Check

REQUIRED_TOOLS = ("pg_dump", "psql")

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
    """
    if missing_tools():
        raise RuntimeError(f"pg_dump not installed or not on PATH -- {INSTALL_HINT}")
    output_dir.mkdir(parents=True, exist_ok=True)
    db = dbname(database_url)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = "_schema" if schema_only else ""
    output_path = output_dir / f"{db}{suffix}_{timestamp}.sql"

    args = ["pg_dump", "--no-owner", "--no-privileges", "-f", str(output_path)]
    if schema_only:
        args.append("--schema-only")
    for schema in schemas or []:
        args.extend(["-n", schema])
    args.append(database_url)

    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(f"pg_dump failed: {result.stderr.strip()}")
    return output_path


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
    return [Check("backup tools (pg_dump/psql)", True, "pg_dump and psql found on PATH")]
