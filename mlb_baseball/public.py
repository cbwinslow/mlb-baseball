"""Small, supported programmatic API for bootstrapping a local research DB.

The package deliberately exposes operations, not a hosted service or a second
ORM.  Callers keep ownership of their PostgreSQL database and can use a normal
psycopg connection for research queries after landing/conforming data.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Literal

from mlb_baseball import conform, doctor, inventory, migrate, model
from mlb_baseball.db import get_connection
from mlb_baseball.registry import CONNECTORS
from mlb_baseball.source_profiles import (
    PROFILES,
    SourceProfileError,
    active_profile,
    require_sources,
)

IngestMode = Literal["bootstrap", "update", "backfill"]


def configure(*, database_url: str | None = None, profile: str | None = None) -> None:
    """Set process-local configuration for a researcher-owned database.

    This only updates environment variables for the current Python process; it
    does not create a database, connect, migrate, or write data.
    """
    if database_url is not None:
        if not database_url.strip():
            raise ValueError("database_url must not be empty")
        os.environ["DATABASE_URL"] = database_url
    if profile is not None:
        if profile not in PROFILES:
            raise SourceProfileError(f"Unknown source profile {profile!r}")
        os.environ["MLB_DATA_PROFILE"] = profile


def migrate_database() -> list[str]:
    """Apply this package's migrations to the configured local database."""
    return migrate.run()


def ingest_source(
    source: str, *, mode: IngestMode = "bootstrap", profile: str | None = None
) -> Mapping[str, int]:
    """Run one registered source through the profile-checked ingestion API."""
    if source not in CONNECTORS:
        raise ValueError(f"unknown source {source!r}; choose one of {sorted(CONNECTORS)}")
    selected_profile = profile or active_profile()
    require_sources(selected_profile, [source], purpose=f"ingest {source}")
    connector = CONNECTORS[source]
    if mode == "bootstrap":
        return connector.bootstrap()
    if mode == "update":
        return connector.update()
    if mode == "backfill":
        backfill = getattr(connector, "backfill_history", None)
        if backfill is None:
            raise ValueError(f"{source} does not support backfill mode")
        return backfill()
    raise ValueError(f"unknown ingestion mode {mode!r}")


def conform_database() -> Mapping[str, int]:
    """Build canonical core relations from the configured database's raw data."""
    return conform.run()


def build_features() -> Mapping[str, int]:
    """Rebuild point-in-time game features in the configured database."""
    return model.run_features()


def run_predictions() -> Mapping[str, int]:
    """Build features and append predictions in the configured database."""
    return model.run()


def health_checks():
    """Return operational checks for the configured database.

    This is read-only. Use the CLI command ``mlb repair-runs`` for the
    explicit state-changing repair of dead-process ingestion records.
    """
    return doctor.run()


def inventory_tables() -> list[dict]:
    """Return live raw/core/gold relation row counts."""
    return inventory.tables()


def inventory_runs() -> list[dict]:
    """Return the latest recorded ingestion run for each source."""
    return inventory.last_runs()


__all__ = [
    "IngestMode",
    "SourceProfileError",
    "configure",
    "build_features",
    "conform_database",
    "get_connection",
    "health_checks",
    "ingest_source",
    "inventory_runs",
    "inventory_tables",
    "migrate_database",
    "run_predictions",
]
