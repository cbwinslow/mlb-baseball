
#!/usr/bin/env python3
"""
================================================================================
Name: baseball/data/sources_v2.py
Date: 2026-05-09
Script Name: Data Source Fetchers (Strategy Pattern)
Version: 2.0.0

Description:
    Specialized fetchers for each data source.
    NO base class - uses duck typing + Protocol for polymorphism.
    Each fetcher optimized for its specific API/access pattern.
    
    Patterns:
    - MLBFetcher: RESTful HTTP calls
    - StatcastFetcher: pybaseball wrapper
    - FanGraphsFetcher: URL-based CSV export
    
    All implement implicit DataFetcher protocol:
    - fetch(query: Query) -> Any
    - fetch_live(query: Query, poll_interval: int) -> Iterator

================================================================================
"""

from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from typing import Any, Iterator, Optional
import logging
import time

import httpx
import pandas as pd
import pybaseball

from baseball.data.endpoints import Endpoint
from baseball.data.query import Query
from baseball.data.config import SourceType


# ============================================================================
# ABSTRACT PROTOCOL (for type hints, not inheritance)
# ============================================================================

class DataFetcher(ABC):
    """
    Abstract protocol for fetchers.
    Used for type hints - implementations don't inherit from this.
    """
    
    @abstractmethod
    def fetch(self, query: Query) -> Any:
        """Fetch data from endpoint."""
        pass
    
    @abstractmethod
    def fetch_live(
        self,
        query: Query,
        poll_interval: int = 10,
    ) -> Iterator[Any]:
        """Fetch data with live polling (yields updates)."""
        pass


# ============================================================================
# MLB FETCHER (RESTful HTTP)
# ============================================================================

class MLBFetcher:
    """Fetch from MLB Stats API via HTTP."""
    
    def __init__(self):
        self.logger = logging.getLogger('baseball.fetch.mlb')
        self.client = httpx.Client(
            timeout=30.0,
            limits=httpx.Limits(max_connections=10),
        )
    
    def fetch(self, query: Query) -> Any:
        """Fetch data from MLB API."""
        self.logger.info(f'Fetching {query.endpoint.name}...')
        
        url = query.endpoint.full_url(**query.params)
        
        try:
            response = self.client.get(url, params=query.params)
            response.raise_for_status()
            
            data = response.json()
            self.logger.info(f'Received {len(str(data))} bytes')
            
            return data
        
        except Exception as e:
            self.logger.error(f'Fetch failed: {e}')
            raise
    
    def fetch_live(
        self,
        query: Query,
        poll_interval: int = 10,
    ) -> Iterator[dict]:
        """
        Poll MLB live game feed.
        
        Yields: Updated game state after each poll
        """
        self.logger.info(f'Starting live poll (interval={poll_interval}s)...')
        
        last_play_id = None
        start_time = datetime.now()
        
        try:
            while True:
                # Fetch current game state
                game_data = self.fetch(query)
                
                # Extract plays since last poll
                all_plays = game_data.get('liveData', {}).get('plays', [])
                
                # Filter to new plays
                if last_play_id is not None:
                    new_plays = [p for p in all_plays if p['about']['index'] > last_play_id]
                else:
                    new_plays = all_plays
                
                # Update last_play_id
                if all_plays:
                    last_play_id = all_plays[-1]['about']['index']
                
                # Yield update
                yield {
                    'timestamp': datetime.now(),
                    'game_state': game_data.get('gameData', {}).get('status', {}),
                    'new_plays': new_plays,
                    'all_plays': all_plays,
                }
                
                # Check if game is finished
                status = game_data.get('gameData', {}).get('status', {}).get('abstractGameCode')
                if status in ('F', 'O'):  # Final or Over
                    self.logger.info('Game finished')
                    break
                
                # Wait before next poll
                time.sleep(poll_interval)
        
        except KeyboardInterrupt:
            self.logger.info('Live polling interrupted')
        finally:
            elapsed = (datetime.now() - start_time).total_seconds()
            self.logger.info(f'Live polling ended after {elapsed:.0f}s')


# ============================================================================
# STATCAST FETCHER (pybaseball wrapper)
# ============================================================================

class StatcastFetcher:
    """Fetch StatCast data via pybaseball."""
    
    def __init__(self):
        self.logger = logging.getLogger('baseball.fetch.statcast')
        pybaseball.cache.enable()
    
    def fetch(self, query: Query) -> pd.DataFrame:
        """Fetch StatCast data."""
        self.logger.info(f'Fetching {query.endpoint.name}...')
        
        try:
            endpoint_type = query.endpoint.endpoint_type
            
            if endpoint_type == 'league':
                # Date range query
                df = pybaseball.statcast(
                    start_dt=str(query.params.get('start_date')),
                    end_dt=str(query.params.get('end_date')),
                )
            
            elif endpoint_type == 'pitcher':
                # Pitcher-specific
                df = pybaseball.statcast_pitcher(
                    pitcher_id=query.params.get('pitcher_id'),
                    start_dt=query.params.get('start_date'),
                    end_dt=query.params.get('end_date'),
                )
            
            elif endpoint_type == 'batter':
                # Batter-specific
                df = pybaseball.statcast_batter(
                    batter_id=query.params.get('batter_id'),
                    start_dt=query.params.get('start_date'),
                    end_dt=query.params.get('end_date'),
                )
            
            else:
                raise ValueError(f'Unknown endpoint type: {endpoint_type}')
            
            if df is not None and not df.empty:
                self.logger.info(f'Received {len(df):,} pitches')
            else:
                self.logger.warning('Empty result')
            
            return df
        
        except Exception as e:
            self.logger.error(f'Fetch failed: {e}')
            raise
    
    def fetch_live(
        self,
        query: Query,
        poll_interval: int = 10,
    ) -> Iterator[pd.DataFrame]:
        """
        Poll StatCast data for live game.
        Note: StatCast updates with delay, not truly live.
        """
        self.logger.warning(
            'StatCast polling supported but data has ~15min delay'
        )
        
        last_count = 0
        
        try:
            while True:
                df = self.fetch(query)
                
                if df is not None and len(df) > last_count:
                    new_rows = df.iloc[last_count:]
                    last_count = len(df)
                    
                    yield new_rows
                
                time.sleep(poll_interval)
        
        except KeyboardInterrupt:
            self.logger.info('Live polling interrupted')


# ============================================================================
# FANGRAPHS FETCHER (URL-based CSV)
# ============================================================================

class FanGraphsFetcher:
    """Fetch FanGraphs data via URL CSV export."""
    
    def __init__(self):
        self.logger = logging.getLogger('baseball.fetch.fangraphs')
        self.client = httpx.Client(
            timeout=30.0,
            headers={
                'User-Agent': 'Mozilla/5.0 (compatible; BaseballBot)',
            },
        )
    
    def fetch(self, query: Query) -> pd.DataFrame:
        """Fetch FanGraphs CSV data."""
        self.logger.info(f'Fetching {query.endpoint.name}...')
        
        try:
            url = self._build_url(query)
            self.logger.debug(f'URL: {url}')
            
            response = self.client.get(url)
            response.raise_for_status()
            
            df = pd.read_csv(StringIO(response.text))
            self.logger.info(f'Received {len(df)} rows')
            
            return df
        
        except Exception as e:
            self.logger.error(f'Fetch failed: {e}')
            raise
    
    def fetch_live(self, query: Query, poll_interval: int = 10) -> Iterator[Any]:
        """FanGraphs doesn't support live data."""
        raise NotImplementedError('FanGraphs does not support live data')
    
    @staticmethod
    def _build_url(query: Query) -> str:
        """Build FanGraphs URL from query params."""
        base = query.endpoint.base_url + query.endpoint.path
        
        # Build query string
        parts = []
        for k, v in query.params.items():
            if isinstance(v, bool):
                v = 1 if v else 0
            parts.append(f'{k}={v}')
        
        return f'{base}?{"&".join(parts)}'


# ============================================================================
# FETCHER REGISTRY
# ============================================================================

class FetcherRegistry:
    """Registry of fetchers per source."""
    
    def __init__(self):
        self.fetchers = {
            SourceType.MLB: MLBFetcher(),
            SourceType.STATCAST: StatcastFetcher(),
            SourceType.FANGRAPHS: FanGraphsFetcher(),
        }
    
    def get_fetcher(self, source: SourceType) -> DataFetcher:
        """Get fetcher for source."""
        fetcher = self.fetchers.get(source)
        if not fetcher:
            raise ValueError(f'No fetcher for {source.value}')
        return fetcher


# Global registry
fetcher_registry = FetcherRegistry()