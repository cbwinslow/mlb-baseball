"""
================================================================================
Source Contracts and Interfaces
Date: 2026-05-09

Protocol definitions for source implementations.
================================================================================
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

from baseball.core.results import DownloadResult, IngestResult, ValidationResult


class SourceContract(ABC):
    """Base contract for all data sources."""

    source_name: str

    @abstractmethod
    def download(self, **params: Any) -> DownloadResult:
        """Download data from source."""
        pass

    @abstractmethod
    def ingest(self, **params: Any) -> IngestResult:
        """Ingest downloaded data."""
        pass

    @abstractmethod
    def validate(self, **params: Any) -> ValidationResult:
        """Validate data."""
        pass


class DownloadContract(ABC):
    """Contract for download operations."""

    @abstractmethod
    def download(self, **params: Any) -> DownloadResult:
        """Execute download operation."""
        pass


class IngestContract(ABC):
    """Contract for ingest operations."""

    @abstractmethod
    def ingest(self, **params: Any) -> IngestResult:
        """Execute ingest operation."""
        pass


class ValidatorContract(ABC):
    """Contract for validation operations."""

    @abstractmethod
    def validate(self, **params: Any) -> ValidationResult:
        """Execute validation operation."""
        pass


class LiveContract(ABC):
    """Contract for live polling operations."""

    @abstractmethod
    async def poll(self, **params: Any) -> Any:
        """Execute live polling."""
        pass
