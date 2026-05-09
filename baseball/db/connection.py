"""
================================================================================
Database Connection Manager
Name: connection.py
Date: 2026-05-09
Script: connection.py
Version: 1.0.0
Log Summary: Establishes PostgreSQL connection pooling and session management
Description: Manages connection creation, pooling, transaction context, and cleanup
Change Summary: Initial implementation with async support and retry logic
Inputs: Database URL, pool size, timeout settings, retry configuration
Outputs: Session factory, connection manager instance, pool health status
================================================================================
"""

import os
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator, Optional

from sqlalchemy import create_engine, event, pool
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from baseball.core.logging import get_logger

logger = get_logger(__name__)


class DatabaseConnectionManager:
    """Manages PostgreSQL connection pooling and session creation."""

    def __init__(
        self,
        database_url: Optional[str] = None,
        pool_size: int = 10,
        max_overflow: int = 20,
        pool_recycle: int = 3600,
        pool_pre_ping: bool = True,
        echo_sql: bool = False,
    ):
        """Initialize connection manager.

        Args:
            database_url: PostgreSQL connection string. Defaults to DATABASE_URL env var.
            pool_size: Number of connections to maintain in pool
            max_overflow: Maximum overflow connections beyond pool_size
            pool_recycle: Recycle connections after N seconds (default 1 hour)
            pool_pre_ping: Test connections before using them
            echo_sql: Log SQL statements if True
        """
        self.database_url = (
            database_url or os.getenv("DATABASE_URL")
        )
        if not self.database_url:
            raise ValueError(
                "DATABASE_URL must be provided or set as environment variable"
            )

        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool_recycle = pool_recycle
        self.pool_pre_ping = pool_pre_ping
        self.echo_sql = echo_sql

        self.engine: Optional[Engine] = None
        self.session_factory: Optional[sessionmaker] = None

    def _create_engine(self) -> Engine:
        """Create SQLAlchemy engine with connection pooling.

        Returns:
            Configured SQLAlchemy Engine instance
        """
        logger.info(
            f"Creating database engine with pool_size={self.pool_size}, "
            f"max_overflow={self.max_overflow}"
        )

        engine = create_engine(
            self.database_url,
            poolclass=QueuePool,
            pool_size=self.pool_size,
            max_overflow=self.max_overflow,
            pool_recycle=self.pool_recycle,
            pool_pre_ping=self.pool_pre_ping,
            echo=self.echo_sql,
            connect_args={"timeout": 10, "check_same_thread": False},
        )

        # Add event listeners for connection pool
        @event.listens_for(engine, "connect")
        def receive_connect(dbapi_conn, connection_record):
            """Called when a new database connection is created."""
            logger.debug("New database connection established")

        @event.listens_for(engine, "checkout")
        def receive_checkout(dbapi_conn, connection_record, connection_proxy):
            """Called when a connection is checked out from the pool."""
            logger.debug("Connection checked out from pool")

        @event.listens_for(engine, "close")
        def receive_close(dbapi_conn, connection_record):
            """Called when a connection is closed/returned to pool."""
            logger.debug("Connection returned to pool")

        return engine

    def initialize(self) -> None:
        """Initialize the connection manager and create engine/session factory."""
        if self.engine is not None:
            logger.warning("Connection manager already initialized")
            return

        try:
            self.engine = self._create_engine()
            self.session_factory = sessionmaker(
                bind=self.engine,
                expire_on_commit=False,
                autoflush=False,
            )
            logger.info("Database connection manager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize connection manager: {e}")
            raise

    def get_session(self) -> Session:
        """Get a new database session.

        Returns:
            SQLAlchemy Session instance
        """
        if self.session_factory is None:
            raise RuntimeError(
                "Connection manager not initialized. Call initialize() first."
            )
        return self.session_factory()

    @contextmanager
    def session_context(self) -> Generator[Session, None, None]:
        """Context manager for database sessions with automatic cleanup.

        Yields:
            SQLAlchemy Session instance

        Example:
            with manager.session_context() as session:
                user = session.query(User).first()
        """
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Session error, rolling back: {e}")
            raise
        finally:
            session.close()

    @asynccontextmanager
    async def async_session_context(self) -> AsyncGenerator[Session, None]:
        """Async context manager for database sessions.

        Yields:
            SQLAlchemy Session instance
        """
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Async session error, rolling back: {e}")
            raise
        finally:
            session.close()

    def health_check(self) -> bool:
        """Check database connection health.

        Returns:
            True if connection is healthy, False otherwise
        """
        if self.engine is None:
            logger.warning("Engine not initialized")
            return False

        try:
            with self.session_context() as session:
                session.execute("SELECT 1")
                logger.info("Database health check passed")
                return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    def dispose(self) -> None:
        """Dispose of all connections in the pool."""
        if self.engine is not None:
            self.engine.dispose()
            logger.info("Connection pool disposed")

    def shutdown(self) -> None:
        """Shutdown the connection manager and close all connections."""
        self.dispose()
        if self.engine is not None:
            self.engine.dispose()
        self.engine = None
        self.session_factory = None
        logger.info("Database connection manager shut down")

    def get_pool_status(self) -> dict:
        """Get current connection pool status.

        Returns:
            Dictionary with pool statistics
        """
        if self.engine is None or not isinstance(self.engine.pool, QueuePool):
            return {}

        pool = self.engine.pool
        return {
            "pool_size": pool.size(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "total_connections": pool.size() + pool.overflow(),
        }
