
"""
================================================================================
Source Registry
Date: 2026-05-09

Central registry for all data source implementations.
================================================================================
"""

from typing import Dict, Optional, Type

from baseball.core.enums import SourceType
from baseball.sources.contracts import SourceContract


class SourceRegistry:
    """Registry for source implementations."""

    _registry: Dict[SourceType, Type[SourceContract]] = {}

    @classmethod
    def register(
        cls,
        source_type: SourceType,
        implementation: Type[SourceContract],
    ) -> None:
        """Register a source implementation."""
        cls._registry[source_type] = implementation

    @classmethod
    def get(cls, source_type: SourceType) -> Optional[Type[SourceContract]]:
        """Get a source implementation."""
        return cls._registry.get(source_type)

    @classmethod
    def list_sources(cls) -> list[SourceType]:
        """List all registered sources."""
        return list(cls._registry.keys())


# Register implementations (will be populated as sources are implemented)
# Example:
# SourceRegistry.register(SourceType.MLB, MLBSource)