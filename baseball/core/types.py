"""
================================================================================
Core Type Definitions
Date: 2026-05-09

Shared types and type aliases used throughout the platform.
================================================================================
"""

from typing import Any, Protocol


class Downloader(Protocol):
    """Protocol for downloader implementations."""

    def download(self, **params: Any) -> Any:
        """Download data from source."""
        ...


class Ingestor(Protocol):
    """Protocol for ingestor implementations."""

    def ingest(self, **params: Any) -> Any:
        """Ingest downloaded data into staging/raw tables."""
        ...


class Validator(Protocol):
    """Protocol for validator implementations."""

    def validate(self, **params: Any) -> Any:
        """Validate data from source."""
        ...
