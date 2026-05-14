"""
================================================================================
Database Schema Utilities
Name: schema.py
Date: 2026-05-11
Script: schema.py
Version: 1.0.0
Log Summary: Schema creation, validation, and introspection utilities
Description: Tools to create all tables and validate schema state
Change Summary: Initial implementation with comprehensive schema validation
Inputs: Database connection, schema definitions
Outputs: Schema creation results, validation reports
================================================================================
"""

from pathlib import Path
from datetime import datetime
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    inspect,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from baseball.core.logging import get_logger
from baseball.db.models import Base

logger = get_logger(__name__)


class SchemaManager:
    """Manage database schema creation and validation."""

    def __init__(self, engine: Engine):
        """Initialize schema manager.

        Args:
            engine: SQLAlchemy Engine instance
        """
        self.engine = engine
        self.inspector = inspect(engine)

    def create_all_tables(self, drop_existing: bool = False) -> bool:
        """Create all tables defined in models.

        Args:
            drop_existing: Drop tables before creating (DESTRUCTIVE)

        Returns:
            True if successful
        """
        try:
            if drop_existing:
                logger.warning("Dropping all tables (DESTRUCTIVE)")
                Base.metadata.drop_all(self.engine)

            logger.info("Creating all tables")
            Base.metadata.create_all(self.engine)
            logger.info("All tables created successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
            return False

    def table_exists(self, table_name: str) -> bool:
        """Check if table exists.

        Args:
            table_name: Name of table to check

        Returns:
            True if table exists
        """
        return table_name in self.inspector.get_table_names()

    def get_table_info(self, table_name: str) -> dict:
        """Get detailed table information.

        Args:
            table_name: Name of table

        Returns:
            Dictionary with table metadata
        """
        if not self.table_exists(table_name):
            return {}

        columns = self.inspector.get_columns(table_name)
        indexes = self.inspector.get_indexes(table_name)
        pk_constraint = self.inspector.get_pk_constraint(table_name)
        fk_constraints = self.inspector.get_foreign_keys(table_name)

        return {
            "name": table_name,
            "columns": columns,
            "column_count": len(columns),
            "indexes": indexes,
            "index_count": len(indexes),
            "primary_key": pk_constraint["constrained_columns"],
            "foreign_keys": fk_constraints,
        }

    def validate_schema(self) -> dict:
        """Validate complete schema state.

        Returns:
            Validation report dictionary
        """
        logger.info("Validating database schema")

        report = {
            "timestamp": None,
            "tables_found": 0,
            "tables_expected": 0,
            "missing_tables": [],
            "extra_tables": [],
            "validation_passed": True,
        }

        # Get expected tables from models
        expected_tables = {
            table.name for table in Base.metadata.tables.values()
        }
        report["tables_expected"] = len(expected_tables)

        # Get actual tables
        actual_tables = set(self.inspector.get_table_names())
        report["tables_found"] = len(actual_tables)

        # Find missing and extra tables
        report["missing_tables"] = list(expected_tables - actual_tables)
        report["extra_tables"] = list(actual_tables - expected_tables)

        if report["missing_tables"]:
            report["validation_passed"] = False
            logger.warning(
                f"Missing tables: {', '.join(report['missing_tables'])}"
            )

        if report["validation_passed"]:
            logger.info("Schema validation passed")
        else:
            logger.error("Schema validation failed")

        return report

    def get_row_counts(self) -> dict:
        """Get row counts for all tables.

        Returns:
            Dictionary with table names and row counts
        """
        counts = {}
        try:
            with Session(self.engine) as session:
                for table in Base.metadata.tables.values():
                    table_name = table.name
                    try:
                        result = session.execute(
                            text(f"SELECT COUNT(*) FROM {table_name}")
                        )
                        count = result.scalar()
                        counts[table_name] = count
                    except Exception as e:
                        logger.warning(f"Failed to count rows in {table_name}: {e}")
                        counts[table_name] = None
        except Exception as e:
            logger.error(f"Failed to get row counts: {e}")

        return counts

    def truncate_all_tables(self, confirm: bool = False) -> bool:
        """Truncate all tables (DESTRUCTIVE).

        Args:
            confirm: Must be True to execute

        Returns:
            True if successful
        """
        if not confirm:
            logger.error("Truncate requires confirm=True")
            return False

        logger.warning("Truncating all tables (DESTRUCTIVE)")
        try:
            with Session(self.engine) as session:
                for table in Base.metadata.tables.values():
                    session.execute(text(f"TRUNCATE TABLE {table.name} CASCADE"))
                session.commit()
                logger.info("All tables truncated")
                return True
        except Exception as e:
            logger.error(f"Failed to truncate tables: {e}")
            return False

    def execute_sql_file(self, sql_file_path: Path) -> bool:
        """Execute SQL commands from file.

        Args:
            sql_file_path: Path to SQL file

        Returns:
            True if successful
        """
        if not sql_file_path.exists():
            logger.error(f"SQL file not found: {sql_file_path}")
            return False

        try:
            with open(sql_file_path) as f:
                sql_content = f.read()

            with Session(self.engine) as session:
                session.execute(text(sql_content))
                session.commit()
                logger.info(f"Executed SQL from {sql_file_path.name}")
                return True
        except Exception as e:
            logger.error(f"Failed to execute SQL file: {e}")
            return False


class SchemaMigration(Base):
    """Track applied schema migrations."""
    
    __tablename__ = "schema_migrations"
    
    migration_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, unique=True)
    applied_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    execution_time_ms = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False)  # success, failed
    error_message = Column(Text, nullable=True)


class SchemaValidation(Base):
    """Track schema validation results."""
    
    __tablename__ = "schema_validation"
    
    validation_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    check_type = Column(String(50), nullable=False)  # table_exists, column_exists, etc.
    object_type = Column(String(50), nullable=False)  # table, column, index, etc.
    object_name = Column(String(255), nullable=False)
    is_valid = Column(Integer, nullable=False)  # 0 for false, 1 for true
    error_message = Column(Text, nullable=True)
    checked_at = Column(DateTime, nullable=False, default=datetime.utcnow)
