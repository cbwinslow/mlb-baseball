
"""
================================================================================
Baseball Analytics Platform
Date: 2026-05-09
Version: 2.0.0

A comprehensive baseball data ingestion, warehouse, and analytics platform.
Supports historical and live MLB data, advanced statistics, modeling, and
prediction workflows.

Canonical namespace: baseball
CLI: baseball [command]

Main modules:
- baseball.core: Shared types, configs, enums, results, exceptions, logging
- baseball.sources: Source adapters (MLB, Retrosheet, StatCast, etc.)
- baseball.services: Orchestration workflows
- baseball.cli: Typer CLI commands
- baseball.db: Database bootstrap and validation

Example:
    from baseball.services.downloads import download_mlb_season
    from baseball.services.live_games import poll_live_game
    
    result = download_mlb_season(season=2025)
    async for update in poll_live_game(game_pk=123456):
        print(update)
================================================================================
"""

__version__ = '2.0.0'
__author__ = 'Baseball Analytics Contributors'
__license__ = 'MIT'

# Core exports - make common items available at package level
from baseball.core.results import (
    DownloadResult,
    IngestResult,
    ValidationResult,
    LiveUpdate,
    CommandResult,
)
from baseball.core.enums import SourceType, DataGranularity
from baseball.core.exceptions import (
    BaseballException,
    SourceException,
    IngestException,
    ValidationException,
)

__all__ = [
    '__version__',
    '__author__',
    '__license__',
    # Results
    'DownloadResult',
    'IngestResult',
    'ValidationResult',
    'LiveUpdate',
    'CommandResult',
    # Enums
    'SourceType',
    'DataGranularity',
    # Exceptions
    'BaseballException',
    'SourceException',
    'IngestException',
    'ValidationException',
]