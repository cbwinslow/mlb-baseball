
"""
================================================================================
Structured Result Objects
Date: 2026-05-09

Dataclasses for structured operation results across the platform.
================================================================================
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from baseball.core.enums import ResultStatus, SourceType, OperationType


@dataclass
class DownloadResult:
    """Result of a download operation."""

    source: SourceType
    operation: OperationType = OperationType.DOWNLOAD
    status: ResultStatus = ResultStatus.SUCCESS

    # Data metrics
    rows_downloaded: int = 0
    bytes_downloaded: int = 0
    files_downloaded: list[Path] = field(default_factory=list)

    # Timing
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # Error info
    error: Optional[str] = None
    error_code: Optional[str] = None
    error_details: Optional[dict[str, Any]] = None

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)
    checksums: dict[str, str] = field(default_factory=dict)  # file: checksum

    @property
    def duration_seconds(self) -> float:
        """Calculate duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0

    @property
    def success(self) -> bool:
        """Check if operation was successful."""
        return self.status == ResultStatus.SUCCESS

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'source': self.source.value,
            'operation': self.operation.value,
            'status': self.status.value,
            'rows_downloaded': self.rows_downloaded,
            'bytes_downloaded': self.bytes_downloaded,
            'files_downloaded': [str(f) for f in self.files_downloaded],
            'duration_seconds': self.duration_seconds,
            'error': self.error,
            'error_code': self.error_code,
            'metadata': self.metadata,
        }


@dataclass
class IngestResult:
    """Result of an ingestion operation."""

    source: SourceType
    status: ResultStatus = ResultStatus.SUCCESS

    # Data metrics
    rows_inserted: int = 0
    rows_updated: int = 0
    rows_skipped: int = 0
    bytes_processed: int = 0

    # Timing
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # Staging/raw info
    staging_table: Optional[str] = None
    raw_table: Optional[str] = None

    # Error info
    error: Optional[str] = None
    error_code: Optional[str] = None

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        """Calculate duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0

    @property
    def success(self) -> bool:
        """Check if operation was successful."""
        return self.status == ResultStatus.SUCCESS

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'source': self.source.value,
            'status': self.status.value,
            'rows_inserted': self.rows_inserted,
            'rows_updated': self.rows_updated,
            'rows_skipped': self.rows_skipped,
            'duration_seconds': self.duration_seconds,
            'error': self.error,
        }


@dataclass
class ValidationResult:
    """Result of a validation operation."""

    source: SourceType
    status: ResultStatus = ResultStatus.SUCCESS

    # Validation metrics
    records_validated: int = 0
    records_valid: int = 0
    records_invalid: int = 0

    # Issues
    issues: list[str] = field(default_factory=list)
    error: Optional[str] = None

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """Check if validation passed."""
        return self.status == ResultStatus.SUCCESS and len(self.issues) == 0


@dataclass
class LiveUpdate:
    """Update from live polling."""

    source: SourceType
    game_pk: int
    timestamp: datetime

    # Change detection
    new_records: list[dict[str, Any]] = field(default_factory=list)
    updated_records: list[dict[str, Any]] = field(default_factory=list)
    deleted_records: list[dict[str, Any]] = field(default_factory=list)

    # Game state
    game_state: Optional[dict[str, Any]] = None
    inning: Optional[int] = None
    inning_state: Optional[str] = None  # top/bottom

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return bool(self.new_records or self.updated_records or self.deleted_records)


@dataclass
class CommandResult:
    """Result of a CLI command."""

    command: str
    status: ResultStatus = ResultStatus.SUCCESS
    message: Optional[str] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """Check if command succeeded."""
        return self.status == ResultStatus.SUCCESS