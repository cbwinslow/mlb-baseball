
"""
================================================================================
Core Exception Types
Date: 2026-05-09

Hierarchical exception classes for the baseball platform.
================================================================================
"""


class BaseballException(Exception):
    """Base exception for all baseball platform errors."""

    pass


class SourceException(BaseballException):
    """Exception from a data source."""

    def __init__(self, source: str, message: str):
        self.source = source
        super().__init__(f'{source}: {message}')


class DownloadException(SourceException):
    """Error during download operation."""

    pass


class IngestException(SourceException):
    """Error during ingestion operation."""

    pass


class ValidationException(SourceException):
    """Error during validation."""

    pass


class ConfigException(BaseballException):
    """Error in configuration."""

    pass


class DatabaseException(BaseballException):
    """Error with database operation."""

    pass


class LiveException(BaseballException):
    """Error in live polling or streaming."""

    pass