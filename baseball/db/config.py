"""
================================================================================
Database Configuration
Name: config.py
Date: 2026-05-09
Script: config.py
Version: 1.0.0
Log Summary: Database configuration models and environment settings
Description: Pydantic models for database configuration with validation
Change Summary: Initial implementation with environment variable support
Inputs: Environment variables for database connection
Outputs: Validated database configuration objects
================================================================================
"""

import os
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class DatabaseConfig(BaseModel):
    """Database connection configuration."""

    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=5432, description="Database port")
    user: str = Field(default="postgres", description="Database user")
    password: str = Field(default="", description="Database password")
    database: str = Field(default="retrosheet", description="Database name")
    pool_size: int = Field(default=10, ge=1, le=100, description="Connection pool size")
    max_overflow: int = Field(
        default=20, ge=0, le=100, description="Max overflow connections"
    )
    pool_recycle: int = Field(
        default=3600, ge=60, description="Pool recycle interval in seconds"
    )
    pool_pre_ping: bool = Field(
        default=True, description="Test connections before using them"
    )
    echo_sql: bool = Field(default=False, description="Log SQL statements")
    ssl_mode: str = Field(
        default="disable", description="SSL connection mode (disable, allow, prefer, require)"
    )

    class Config:
        """Pydantic configuration."""
        env_prefix = "DB_"

    @field_validator("port")
    @classmethod
    def validate_port(cls, v):
        """Validate port number."""
        if not 1 <= v <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

    @field_validator("ssl_mode")
    @classmethod
    def validate_ssl_mode(cls, v):
        """Validate SSL mode."""
        valid_modes = {"disable", "allow", "prefer", "require"}
        if v not in valid_modes:
            raise ValueError(f"SSL mode must be one of {valid_modes}")
        return v

    @property
    def connection_url(self) -> str:
        """Generate PostgreSQL connection URL."""
        auth = f"{self.user}"
        if self.password:
            auth += f":{self.password}"

        url = f"postgresql://{auth}@{self.host}:{self.port}/{self.database}"

        # Add SSL mode parameter
        if self.ssl_mode != "disable":
            url += f"?sslmode={self.ssl_mode}"

        return url

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """Load configuration from environment variables.

        Environment variables:
        - DB_HOST: Database host (default: localhost)
        - DB_PORT: Database port (default: 5432)
        - DB_USER: Database user (default: postgres)
        - DB_PASSWORD: Database password (default: "")
        - DB_DATABASE: Database name (default: retrosheet)
        - DB_POOL_SIZE: Connection pool size (default: 10)
        - DB_MAX_OVERFLOW: Max overflow connections (default: 20)
        - DB_POOL_RECYCLE: Pool recycle interval in seconds (default: 3600)
        - DB_POOL_PRE_PING: Test connections (default: true)
        - DB_ECHO_SQL: Log SQL (default: false)
        - DB_SSL_MODE: SSL mode (default: disable)

        Returns:
            DatabaseConfig instance
        """
        return cls(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_DATABASE", "retrosheet"),
            pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "3600")),
            pool_pre_ping=os.getenv("DB_POOL_PRE_PING", "true").lower() == "true",
            echo_sql=os.getenv("DB_ECHO_SQL", "false").lower() == "true",
            ssl_mode=os.getenv("DB_SSL_MODE", "disable"),
        )


class MigrationConfig(BaseModel):
    """Migration and schema configuration."""

    sql_directory: str = Field(default="sql", description="Path to SQL scripts")
    migration_table: str = Field(
        default="schema_migrations", description="Table for tracking migrations"
    )
    auto_migrate: bool = Field(
        default=False, description="Auto-run migrations on startup"
    )
    skip_validation: bool = Field(
        default=False, description="Skip schema validation"
    )

    class Config:
        """Pydantic configuration."""
        env_prefix = "MIGRATION_"

    @classmethod
    def from_env(cls) -> "MigrationConfig":
        """Load configuration from environment variables."""
        return cls(
            sql_directory=os.getenv("MIGRATION_SQL_DIRECTORY", "sql"),
            migration_table=os.getenv("MIGRATION_TABLE", "schema_migrations"),
            auto_migrate=os.getenv("MIGRATION_AUTO_MIGRATE", "false").lower() == "true",
            skip_validation=os.getenv("MIGRATION_SKIP_VALIDATION", "false").lower() == "true",
        )


class SourceMetadataConfig(BaseModel):
    """Configuration for source metadata tracking."""

    track_provenance: bool = Field(
        default=True, description="Track source, endpoint, timestamp of data"
    )
    track_checksums: bool = Field(
        default=True, description="Store checksums/versions of source files"
    )
    raw_retention_days: int = Field(
        default=90, description="Days to retain raw payloads (0 = indefinite)"
    )
    staging_retention_days: int = Field(
        default=180, description="Days to retain staging data (0 = indefinite)"
    )

    class Config:
        """Pydantic configuration."""
        env_prefix = "SOURCE_"

    @classmethod
    def from_env(cls) -> "SourceMetadataConfig":
        """Load configuration from environment variables."""
        return cls(
            track_provenance=os.getenv("SOURCE_TRACK_PROVENANCE", "true").lower() == "true",
            track_checksums=os.getenv("SOURCE_TRACK_CHECKSUMS", "true").lower() == "true",
            raw_retention_days=int(os.getenv("SOURCE_RAW_RETENTION_DAYS", "90")),
            staging_retention_days=int(os.getenv("SOURCE_STAGING_RETENTION_DAYS", "180")),
        )
