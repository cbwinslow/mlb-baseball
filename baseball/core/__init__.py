"""Core shared types, configurations, and utilities.

This package exposes the fundamental building blocks used across all
baseball source adapters, services, and CLI commands:
  - Result dataclasses (DownloadResult, IngestResult, ValidationResult, etc.)
  - Enumerations (OperationType, ResultStatus, SourceType, DataGranularity)
  - Custom exceptions (BaseballException, DownloadException, IngestException, etc.)
  - Logging configuration (get_logger)
"""

from baseball.core.results import (
    CommandResult,
    DownloadResult,
    IngestResult,
    LiveUpdate,
    ValidationResult,
)
from baseball.core.exceptions import (
    BaseballException,
    ConfigException,
    DatabaseException,
    DownloadException,
    IngestException,
    LiveException,
    SourceException,
    ValidationException,
)
from baseball.core.logging import get_logger

__all__ = [
    # Result types
    "DownloadResult",
    "IngestResult",
    "ValidationResult",
    "LiveUpdate",
    "CommandResult",
    # Exceptions
    "BaseballException",
    "SourceException",
    "DownloadException",
    "IngestException",
    "ValidationException",
    "ConfigException",
    "DatabaseException",
    "LiveException",
    # Logging
    "get_logger",
]
