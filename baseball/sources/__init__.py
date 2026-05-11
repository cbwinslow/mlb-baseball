"""Data source adapters and downloaders.

This package contains all external data source integrations:
  - mlb        : MLB Stats API (schedules, game data, player stats)
  - retrosheet  : Retrosheet historical event files and game logs
  - statcast    : Baseball Savant / StatCast pitch-level data
  - common      : Shared base classes for downloaders and ingestors
  - espn        : ESPN scoreboard and game data
  - fangraphs   : FanGraphs advanced statistics
  - lahman      : Lahman historical baseball database
  - weather     : Weather data for game context
"""

from baseball.sources.mlb import MLBDownloader, MLBIngestor
from baseball.sources.retrosheet import (
    RetroEventFileDownloader,
    RetroEventFileIngestor,
)
from baseball.sources.statcast import StatcastDownloader, StatcastIngestor

__all__ = [
    # MLB Stats API
    "MLBDownloader",
    "MLBIngestor",
    # Retrosheet
    "RetroEventFileDownloader",
    "RetroEventFileIngestor",
    # StatCast
    "StatcastDownloader",
    "StatcastIngestor",
]
