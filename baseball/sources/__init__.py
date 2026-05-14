"""Data source adapters and downloaders.

This package contains all external data source integrations:
  - mlb        : MLB Stats API (schedules, game data, player stats)
  - retrosheet  : Retrosheet historical event files and game logs
  - statcast    : Baseball Savant / StatCast pitch-level data
  - espn        : ESPN scoreboard and game data
  - fangraphs   : FanGraphs advanced statistics
  - lahman      : Lahman historical baseball database
  - weather     : Weather data for game context
  - common      : Shared base classes for downloaders and ingestors

All sources are auto-registered with SourceRegistry on import.
"""

from baseball.core.enums import SourceType
from baseball.sources.registry import SourceRegistry

# --- MLB Stats API ---
from baseball.sources.mlb import MLBDownloader, MLBIngestor

SourceRegistry.register(
    SourceType.MLB,
    downloader_class=MLBDownloader,
    ingestor_class=MLBIngestor,
    description="MLB Stats API: schedules, game data, player stats, standings",
)

# --- Retrosheet ---
from baseball.sources.retrosheet import (
    RetroEventFileDownloader,
    RetroEventFileIngestor,
)

SourceRegistry.register(
    SourceType.RETROSHEET,
    downloader_class=RetroEventFileDownloader,
    ingestor_class=RetroEventFileIngestor,
    description="Retrosheet: historical play-by-play event files and game logs",
)

# --- StatCast / Baseball Savant ---
from baseball.sources.statcast import StatcastDownloader, StatcastIngestor

SourceRegistry.register(
    SourceType.STATCAST,
    downloader_class=StatcastDownloader,
    ingestor_class=StatcastIngestor,
    description="Baseball Savant / StatCast: pitch-level tracking data",
)

# --- ESPN ---
from baseball.sources.espn.downloader import ESPNDownloader

SourceRegistry.register(
    SourceType.ESPN,
    downloader_class=ESPNDownloader,
    ingestor_class=None,
    description="ESPN API: scoreboard and game data",
)

# --- FanGraphs ---
from baseball.sources.fangraphs.downloader import FanGraphsDownloader

SourceRegistry.register(
    SourceType.FANGRAPHS,
    downloader_class=FanGraphsDownloader,
    ingestor_class=None,
    description="FanGraphs: advanced batting and pitching statistics via CSV export",
)

# --- Lahman ---
from baseball.sources.lahman.downloader import LahmanDownloader

SourceRegistry.register(
    SourceType.LAHMAN,
    downloader_class=LahmanDownloader,
    ingestor_class=None,
    description="Lahman Baseball Database: comprehensive historical statistics",
)

# --- Weather ---
from baseball.sources.weather.downloader import WeatherDownloader

SourceRegistry.register(
    SourceType.WEATHER,
    downloader_class=WeatherDownloader,
    ingestor_class=None,
    description="NOAA Weather API: game-day weather forecasts by venue",
)

__all__ = [
    # Registry
    "SourceRegistry",
    # MLB Stats API
    "MLBDownloader",
    "MLBIngestor",
    # Retrosheet
    "RetroEventFileDownloader",
    "RetroEventFileIngestor",
    # StatCast
    "StatcastDownloader",
    "StatcastIngestor",
    # ESPN
    "ESPNDownloader",
    # FanGraphs
    "FanGraphsDownloader",
    # Lahman
    "LahmanDownloader",
    # Weather
    "WeatherDownloader",
]
