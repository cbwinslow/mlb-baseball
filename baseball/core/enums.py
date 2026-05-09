"""
================================================================================
Core Enumerations
Date: 2026-05-09

Shared enum types used across the baseball platform.
================================================================================
"""

from enum import Enum


class SourceType(str, Enum):
    """Baseball data source types."""

    MLB = "mlb"
    RETROSHEET = "retrosheet"
    STATCAST = "statcast"
    LAHMAN = "lahman"
    FANGRAPHS = "fangraphs"
    ESPN = "espn"
    WEATHER = "weather"
    PARK_FACTORS = "park_factors"


class DataGranularity(str, Enum):
    """Data download/ingest granularity levels."""

    LEAGUE = "league"  # All teams/players for a season
    DIVISION = "division"  # Division-level data
    TEAM = "team"  # Team-specific data
    PLAYER = "player"  # Individual player level
    PITCHER = "pitcher"  # Pitcher-specific level
    BATTER = "batter"  # Batter-specific level
    GAME = "game"  # Individual game
    PLAY = "play"  # Play-by-play
    PITCH = "pitch"  # Pitch-level (StatCast)


class OperationType(str, Enum):
    """Type of operation being performed."""

    DOWNLOAD = "download"
    INGEST = "ingest"
    NORMALIZE = "normalize"
    VALIDATE = "validate"
    BRIDGE = "bridge"


class ResultStatus(str, Enum):
    """Result status."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"
