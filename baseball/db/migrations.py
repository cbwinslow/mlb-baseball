"""
================================================================================
Database Migrations Manager
Name: migrations.py
Date: 2026-05-09
Script: migrations.py
Version: 1.0.0
Log Summary: Database schema migrations and versioning
Description: Loads and applies SQL migration files in version order
Change Summary: Initial implementation with rollback and validation
Inputs: SQL migration directory, connection manager
Outputs: Applied migration tracking, schema version state
================================================================================
"""

import hashlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from baseball.core.logging import get_logger
from baseball.db.schema import SchemaMigration, SchemaValidation

logger = get_logger(__name__)


class MigrationManager:
    """Manages database schema migrations and versioning."""

    def __init__(self, session: Session, sql_directory: Path = Path("sql")):
        """Initialize migration manager.

        Args:
            session: SQLAlchemy session for executing migrations
            sql_directory: Path to SQL migration scripts directory
        """
        self.session = session
        self.sql_directory = Path(sql_directory)
        self.migrations: Dict[str, str] = {}

    def _discover_migrations(self) -> Dict[str, Path]:
        """Discover all migration files in sql directory.

        Returns:
            Dictionary mapping version number to file path
        """
        if not self.sql_directory.exists():
            logger.warning(f"SQL directory not found: {self.sql_directory}")
            return {}

        migrations = {}
        # Pattern: 10_extensions.sql, 20_schemas.sql, etc.
        for sql_file in sorted(self.sql_directory.glob("*.sql")):
            # Extract version number from filename
            parts = sql_file.name.split("_", 1)
            if parts[0].isdigit():
                version = parts[0]
                migrations[version] = sql_file

        logger.info(f"Discovered {len(migrations)} migration files")
        return migrations

    def _get_migration_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of migration file.

        Args:
            file_path: Path to migration file

        Returns:
            Hex digest of file content
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _load_migration_sql(self, file_path: Path) -> str:
        """Load SQL content from migration file.

        Args:
            file_path: Path to SQL file

        Returns:
            SQL content as string
        """
        with open(file_path, "r") as f:
            return f.read()

    def get_applied_migrations(self) -> List[str]:
        """Get list of already-applied migrations.

        Returns:
            List of migration names that have been applied
        """
        try:
            applied = (
                self.session.query(SchemaMigration)
                .filter(SchemaMigration.status == "success")
                .order_by(SchemaMigration.applied_at)
                .all()
            )
            return [m.name for m in applied]
        except Exception as e:
            logger.warning(f"Could not query applied migrations: {e}")
            return []

    def get_pending_migrations(self) -> List[Tuple[str, Path]]:
        """Get list of pending migrations to apply.

        Returns:
            List of tuples (version, file_path) for unapplied migrations
        """
        discovered = self._discover_migrations()
        applied = self.get_applied_migrations()

        pending = []
        for version in sorted(discovered.keys()):
            file_path = discovered[version]
            if file_path.name not in applied:
                pending.append((version, file_path))

        return pending

    def apply_migration(self, version: str, file_path: Path) -> bool:
        """Apply a single migration.

        Args:
            version: Version number of migration
            file_path: Path to migration SQL file

        Returns:
            True if migration applied successfully
        """
        logger.info(f"Applying migration {version}: {file_path.name}")

        try:
            start_time = datetime.utcnow()
            sql_content = self._load_migration_sql(file_path)

            # Execute SQL (split by semicolon to handle multiple statements)
            statements = [s.strip() for s in sql_content.split(";") if s.strip()]
            for statement in statements:
                self.session.execute(statement)

            self.session.commit()

            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            checksum = self._get_migration_checksum(file_path)

            # Record migration in metadata
            migration = SchemaMigration(
                migration_id=str(uuid.uuid4()),
                name=file_path.name,
                applied_at=start_time,
                execution_time_ms=int(execution_time),
                status="success",
            )
            self.session.add(migration)
            self.session.commit()

            logger.info(
                f"Migration {version} applied successfully in {execution_time:.0f}ms"
            )
            return True

        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to apply migration {version}: {e}")

            # Record failure
            migration = SchemaMigration(
                migration_id=str(uuid.uuid4()),
                name=file_path.name,
                applied_at=datetime.utcnow(),
                status="failed",
                error_message=str(e),
            )
            self.session.add(migration)
            self.session.commit()

            return False

    def apply_all_pending(self) -> Tuple[int, int]:
        """Apply all pending migrations in order.

        Returns:
            Tuple of (migrations_applied, migrations_failed)
        """
        pending = self.get_pending_migrations()
        logger.info(f"Found {len(pending)} pending migrations")

        applied = 0
        failed = 0

        for version, file_path in pending:
            if self.apply_migration(version, file_path):
                applied += 1
            else:
                failed += 1
                # Stop on first failure
                break

        logger.info(f"Applied {applied} migrations, {failed} failed")
        return applied, failed

    def validate_schema(self) -> bool:
        """Validate that all required schema objects exist.

        Returns:
            True if schema is valid
        """
        logger.info("Validating database schema")

        required_tables = [
            "players",
            "teams",
            "parks",
            "games",
            "events",
            "pitches",
            "source_crosswalk",
            "raw_payload_metadata",
            "schema_migrations",
            "schema_validation",
        ]

        try:
            # Check each required table
            inspector_result = self.session.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
            existing_tables = {row[0] for row in inspector_result}

            validation_id = str(uuid.uuid4())
            is_valid = True

            for table_name in required_tables:
                if table_name in existing_tables:
                    status = "success"
                    is_valid_check = True
                else:
                    status = "failed"
                    is_valid_check = False
                    is_valid = False

                # Record validation result
                validation = SchemaValidation(
                    validation_id=str(uuid.uuid4()),
                    check_type="table_exists",
                    object_type="table",
                    object_name=table_name,
                    is_valid=is_valid_check,
                    error_message=None if is_valid_check else f"Table {table_name} not found",
                    checked_at=datetime.utcnow(),
                )
                self.session.add(validation)

            self.session.commit()

            if is_valid:
                logger.info("Schema validation passed")
            else:
                logger.error("Schema validation failed - missing tables")

            return is_valid

        except Exception as e:
            logger.error(f"Schema validation error: {e}")
            return False

    def get_migration_status(self) -> Dict:
        """Get current migration status.

        Returns:
            Dictionary with status information
        """
        return {
            "applied_migrations": len(self.get_applied_migrations()),
            "pending_migrations": len(self.get_pending_migrations()),
            "total_discovered": len(self._discover_migrations()),
        }
