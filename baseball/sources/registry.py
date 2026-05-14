"""
================================================================================
Source Registry
Date: 2026-05-09 (updated 2026-05-12)

Central registry for all data source implementations.
Maps SourceType -> (downloader_class, ingestor_class) pairs.

All sources are auto-registered when this module is imported via
baseball/sources/__init__.py.
================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from baseball.core.enums import SourceType
from baseball.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SourceEntry:
    """Registry entry holding the downloader and ingestor class for one source."""

    source_type: SourceType
    downloader_class: Optional[type] = None
    ingestor_class: Optional[type] = None
    description: str = ""

    def get_downloader(self, **kwargs: Any) -> Any:
        """Instantiate and return the downloader."""
        if self.downloader_class is None:
            raise NotImplementedError(f"No downloader registered for {self.source_type}")
        return self.downloader_class(**kwargs)

    def get_ingestor(self, **kwargs: Any) -> Any:
        """Instantiate and return the ingestor."""
        if self.ingestor_class is None:
            raise NotImplementedError(f"No ingestor registered for {self.source_type}")
        return self.ingestor_class(**kwargs)


class SourceRegistry:
    """Registry mapping SourceType to downloader/ingestor implementations."""

    _registry: dict[SourceType, SourceEntry] = {}

    @classmethod
    def register(
        cls,
        source_type: SourceType,
        downloader_class: Optional[type] = None,
        ingestor_class: Optional[type] = None,
        description: str = "",
    ) -> None:
        """Register a source implementation.

        Args:
            source_type: The SourceType enum value.
            downloader_class: Class responsible for downloading raw data.
            ingestor_class: Class responsible for ingesting data into the DB.
            description: Human-readable description of the source.
        """
        entry = SourceEntry(
            source_type=source_type,
            downloader_class=downloader_class,
            ingestor_class=ingestor_class,
            description=description,
        )
        cls._registry[source_type] = entry
        logger.debug(f"Registered source: {source_type.value}")

    @classmethod
    def get(cls, source_type: SourceType) -> Optional[SourceEntry]:
        """Get the SourceEntry for a given SourceType."""
        return cls._registry.get(source_type)

    @classmethod
    def get_downloader(cls, source_type: SourceType, **kwargs: Any) -> Any:
        """Get an instantiated downloader for a source."""
        entry = cls.get(source_type)
        if entry is None:
            raise KeyError(f"No source registered for: {source_type}")
        return entry.get_downloader(**kwargs)

    @classmethod
    def get_ingestor(cls, source_type: SourceType, **kwargs: Any) -> Any:
        """Get an instantiated ingestor for a source."""
        entry = cls.get(source_type)
        if entry is None:
            raise KeyError(f"No source registered for: {source_type}")
        return entry.get_ingestor(**kwargs)

    @classmethod
    def list_sources(cls) -> list[SourceType]:
        """Return list of all registered SourceTypes."""
        return list(cls._registry.keys())

    @classmethod
    def is_registered(cls, source_type: SourceType) -> bool:
        """Check whether a source type is registered."""
        return source_type in cls._registry

    @classmethod
    def summary(cls) -> dict[str, dict[str, bool]]:
        """Return a summary of registered sources and their capabilities."""
        return {
            entry.source_type.value: {
                "downloader": entry.downloader_class is not None,
                "ingestor": entry.ingestor_class is not None,
                "description": entry.description,
            }
            for entry in cls._registry.values()
        }
