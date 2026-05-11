"""High-level orchestration and workflow services.

Provides convenience functions that orchestrate across multiple data sources:
  - downloads    : Download workflows for all sources
  - normalization: Cross-source data normalization and deduplication
  - validation   : Data quality and completeness checks
  - bridging     : Connecting source data to the database layer
  - live_games   : Live game polling and real-time data feeds
"""

from baseball.services import (
    bridging,
    downloads,
    live_games,
    normalization,
    validation,
)

__all__ = [
    "bridging",
    "downloads",
    "live_games",
    "normalization",
    "validation",
]
