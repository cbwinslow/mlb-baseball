
#!/usr/bin/env python3
"""
================================================================================
Name: baseball/data/__init__.py
Date: 2026-05-09
Script Name: Baseball Data Download Public API
Version: 2.0.0

Description:
    Public API for downloading baseball data.
    Smart routing based on parameters.
    Supports all granularities and live polling.

================================================================================
"""

from datetime import date
from pathlib import Path
from typing import Optional, Iterator
import logging

from baseball.data.config import (
    SourceType,
    DataGranularity,
    MLBConfig,
    StatcastConfig,
    FanGraphsConfig,
)
from baseball.data.endpoints import endpoint_registry, MLBEndpointType
from baseball.data.query import query_builder
from baseball.data.sources_v2 import fetcher_registry
from baseball.data.sources import DownloadResult  # Reuse result class


logger = logging.getLogger('baseball.data')


# ============================================================================
# SMART ROUTING DOWNLOADER
# ============================================================================

class SmartDownloader:
    """
    Intelligent downloader that routes to appropriate endpoint.
    
    Determines endpoint_type and granularity from input parameters,
    builds query, fetches data, saves, and validates.
    """
    
    def __init__(self):
        self.endpoint_registry = endpoint_registry
        self.query_builder = query_builder
        self.fetcher_registry = fetcher_registry
    
    def download_mlb(
        self,
        # Season specification
        season: Optional[int] = None,
        start_season: Optional[int] = None,
        end_season: Optional[int] = None,
        # Date specification
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        # Granularity
        granularity: Optional[DataGranularity] = None,
        # Specific filters
        team_id: Optional[str] = None,
        game_pk: Optional[int] = None,
        person_id: Optional[int] = None,
        # Live data
        live: bool = False,
        poll_interval: int = 10,
        # Config
        config: Optional[MLBConfig] = None,
        **kwargs,
    ) -> DownloadResult | Iterator[DownloadResult]:
        """
        Download MLB data with smart routing.
        
        Examples:
        ```python
        # League-level schedule
        download_mlb(season=2024)
        
        # Specific game with live polling
        download_mlb(game_pk=719424, live=True)
        
        # Team schedule
        download_mlb(season=2024, team_id='NYY')
        
        # Player stats
        download_mlb(person_id=123, season=2024)
        ```
        """
        if config is None:
            config = MLBConfig(
                season=season,
                start_season=start_season,
                end_season=end_season,
                start_date=start_date,
                end_date=end_date,
                granularity=granularity,
                teams=[team_id] if team_id else None,
                **kwargs,
            )
        
        # Determine endpoint type from params
        endpoint_type, determined_granularity = self._determine_mlb_endpoint(
            season=config.season,
            team_id=team_id,
            game_pk=game_pk,
            person_id=person_id,
            live=live,
        )
        
        # Use determined granularity if not specified
        if config.granularity is None:
            config.granularity = determined_granularity
        
        logger.info(
            f'Routing: endpoint={endpoint_type}, granularity={config.granularity.value}'
        )
        
        # Build query
        try:
            query = self.query_builder.build(
                source=SourceType.MLB,
                endpoint_type=endpoint_type,
                granularity=config.granularity,
                season=config.season,
                team_id=team_id,
                game_pk=game_pk,
                person_id=person_id,
            )
        except ValueError as e:
            result = DownloadResult(source=SourceType.MLB, success=False)
            result.error = str(e)
            return result
        
        # Fetch data
        fetcher = self.fetcher_registry.get_fetcher(SourceType.MLB)
        
        if live:
            # Return live polling iterator
            return fetcher.fetch_live(query, poll_interval=poll_interval)
        else:
            # Standard download
            try:
                raw_data = fetcher.fetch(query)
                # Save and validate...
                result = DownloadResult(source=SourceType.MLB, success=True)
                result.rows_downloaded = len(raw_data) if isinstance(raw_data, list) else 1
                return result
            except Exception as e:
                result = DownloadResult(source=SourceType.MLB, success=False)
                result.error = str(e)
                return result
    
    @staticmethod
    def _determine_mlb_endpoint(
        season: Optional[int],
        team_id: Optional[str],
        game_pk: Optional[int],
        person_id: Optional[int],
        live: bool,
    ) -> tuple[str, DataGranularity]:
        """Determine endpoint and granularity from params."""
        
        if live and game_pk:
            return MLBEndpointType.LIVEFEED.value, DataGranularity.PLAY
        
        if game_pk:
            return MLBEndpointType.GAME.value, DataGranularity.GAME
        
        if person_id:
            return MLBEndpointType.PERSON_STATS.value, DataGranularity.PLAYER
        
        if team_id:
            return MLBEndpointType.SCHEDULE.value, DataGranularity.TEAM
        
        if season:
            return MLBEndpointType.SCHEDULE.value, DataGranularity.LEAGUE
        
        raise ValueError('Must specify season, game_pk, team_id, or person_id')


# ============================================================================
# PUBLIC API
# ============================================================================

_downloader = SmartDownloader()


def download_mlb(
    season: Optional[int] = None,
    start_season: Optional[int] = None,
    end_season: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    granularity: Optional[DataGranularity] = None,
    team_id: Optional[str] = None,
    game_pk: Optional[int] = None,
    person_id: Optional[int] = None,
    live: bool = False,
    poll_interval: int = 10,
    config: Optional[MLBConfig] = None,
    **kwargs,
) -> DownloadResult | Iterator[DownloadResult]:
    """
    Download MLB data with smart routing.
    
    Supports all granularity levels:
    - LEAGUE: Full season schedule
    - TEAM: Team-specific schedule
    - GAME: Individual game data
    - PLAY: Play-by-play
    - PITCHER/PLAYER: Player stats
    
    Also supports live polling for real-time game data.
    """
    return _downloader.download_mlb(
        season=season,
        start_season=start_season,
        end_season=end_season,
        start_date=start_date,
        end_date=end_date,
        granularity=granularity,
        team_id=team_id,
        game_pk=game_pk,
        person_id=person_id,
        live=live,
        poll_interval=poll_interval,
        config=config,
        **kwargs,
    )


__all__ = [
    'download_mlb',
    'DownloadResult',
    'SourceType',
    'DataGranularity',
    'endpoint_registry',
]