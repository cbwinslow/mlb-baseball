
"""
================================================================================
Retrosheet Data Models
Date: 2026-05-09

Pydantic models for Retrosheet event files and parsed data.
================================================================================
"""

from datetime import date, datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class RetroEventFileRequest(BaseModel):
    """Request model for Retrosheet event file downloads."""

    season: int = Field(..., ge=1871, le=2100, description='Season year')
    start_season: Optional[int] = Field(None, ge=1871, description='Start season for range')
    end_season: Optional[int] = Field(None, ge=1871, description='End season for range')
    teams: Optional[list[str]] = Field(None, description='Team abbreviations (e.g., NYY, BOS)')
    extract_events: bool = Field(True, description='Extract individual events')


class RetroEventLine(BaseModel):
    """A single event line from Retrosheet file."""

    line_type: str  # id, version, info, start, sub, play, com, data
    season: int
    game_id: str
    inning: Optional[int] = None
    home_away: Optional[int] = None  # 0=away, 1=home
    player_id: Optional[str] = None
    event_type: Optional[str] = None
    description: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RetroGameEvent(BaseModel):
    """A parsed game event."""

    game_id: str
    date: date
    season: int
    home_team: str
    away_team: str
    inning: int
    inning_state: str  # top, bottom
    pitcher_id: Optional[str] = None
    pitcher_name: Optional[str] = None
    batter_id: Optional[str] = None
    batter_name: Optional[str] = None
    event_code: str
    event_description: str
    runs_scored: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RetroGameLog(BaseModel):
    """A game log summary from Retrosheet."""

    game_id: str
    date: date
    season: int
    day_of_week: str
    home_team: str
    home_runs: int
    away_team: str
    away_runs: int
    game_duration: int  # minutes
    attendance: Optional[int] = None
    weather: Optional[str] = None
    wind_direction: Optional[str] = None
    wind_speed: Optional[int] = None
    temperature: Optional[int] = None