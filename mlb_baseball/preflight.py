"""Read-only readiness report for a planned bootstrap."""

import shutil
from pathlib import Path

import psycopg

from mlb_baseball import chadwick_tools, migrate
from mlb_baseball.config import Settings
from mlb_baseball.health import Check
from mlb_baseball.registry import CONNECTORS


def _directory_check(path: Path, name: str) -> Check:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".mlb_preflight_probe"
        probe.write_text("ok")
        probe.unlink()
        free_gb = shutil.disk_usage(path).free / (1024**3)
        return Check(name, True, f"{path} writable; {free_gb:.1f}GB free")
    except OSError as exc:
        return Check(name, False, f"{path} is not writable: {exc}")


def _database_check(settings: Settings) -> list[Check]:
    if not settings.database_url:
        return [
            Check("database", False, "DATABASE_URL is missing; set it in .env or the environment")
        ]
    try:
        with psycopg.connect(settings.database_url) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.execute("SELECT to_regclass('public.schema_migrations')")
            row = cur.fetchone()
            has_ledger = row is not None and row[0] is not None
            if not has_ledger:
                return [Check("database", True, "reachable; migrations have not been applied")]
            cur.execute("SELECT version FROM public.schema_migrations")
            applied = {row[0] for row in cur.fetchall()}
    except Exception as exc:
        return [Check("database", False, f"cannot connect using DATABASE_URL: {exc}")]
    pending = {path.name for path in migrate.MIGRATIONS_DIR.glob("*.sql")} - applied
    detail = (
        "reachable; migrations current"
        if not pending
        else f"reachable; {len(pending)} migration(s) pending"
    )
    return [Check("database", True, detail)]


def run(
    settings: Settings, sources: list[str] | None, with_conform: bool
) -> tuple[list[Check], list[str]]:
    """Return checks and the exact non-mutating plan; never calls a connector."""
    selected = sources or list(CONNECTORS)
    invalid = sorted(set(selected) - set(CONNECTORS))
    source_detail = (
        "selected: " + ", ".join(selected)
        if not invalid
        else f"unknown: {', '.join(invalid)}"
    )
    checks = [
        Check("sources", not invalid, source_detail),
        _directory_check(settings.download_dir, "download directory"),
        _directory_check(settings.log_dir, "log directory"),
    ]
    missing = chadwick_tools.missing_tools()
    checks.append(
        Check(
            "Chadwick tools",
            not missing,
            "available" if not missing else f"missing: {', '.join(missing)}",
        )
    )
    checks.extend(_database_check(settings))
    commands = ["mlb migrate"]
    if sources:
        commands.extend(
            f"mlb ingest {source} --mode bootstrap" for source in selected if source in CONNECTORS
        )
    else:
        commands.append("mlb bootstrap")
    if with_conform:
        commands.append("mlb conform  # only after raw-layer doctor checks are healthy")
    commands.extend(["mlb doctor", "mlb inventory"])
    return checks, commands
