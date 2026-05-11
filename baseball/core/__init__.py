"""Core shared types, configurations, and utilities.

This package exposes the fundamental building blocks used across all
baseball source adapters, services, and CLI commands:
  - Result dataclasses (DownloadResult, IngestResult, ValidationResult, etc.)
  - Enumerations (OperationType, ResultStatus, SourceType)
  - Custom exceptions (BaseballError, DownloadError, IngestError, etc.)
  - Shared type aliases (types.py)
  - Logging configuration (get_logger)
"""

from baseball.core.results import (
    CommandResult,
    DownloadResult,
    IngestResult,
    LiveUpdate,
    ValidationResult,
)
from baseball.core.logging import get_logger

__all__ = [
    # Result types
    "DownloadResult",
    "IngestResult",
    "ValidationResult",
    "LiveUpdate",
    "CommandResult",
    # Logging
    "get_logger",
]
