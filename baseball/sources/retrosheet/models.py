"""
================================================================================
Retrosheet Data Models
Date: 2026-05-09

Pydantic models for Retrosheet event files and parsed data.
================================================================================
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class RetroEventFileRequest(BaseModel):
    """Request model for Retrosheet event file downloads."""

    season: int = Field(..., ge=1871, le=2100, description="Season year")
    start_season: int | None = Field(
        None, ge=1871, description="Start season for range"
    )
    end_season: int | None = Field(None, ge=1871, description="End season for range")
    teams: list[str] | None = Field(
        None, description="Team abbreviations (e.g., NYY, BOS)"
    )
    extract_events: bool = Field(True, description="Extract individual events")


class RetroEventLine(BaseModel):
    """A single event line from Retrosheet file."""

    line_type: str  # id, version, info, start, sub, play, com, data
    season: int
    game_id: str
    inning: int | None = None
    home_away: int | None = None  # 0=away, 1=home
    player_id: str | None = None
    event_type: str | None = None
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetroGameEvent(BaseModel):
    """A parsed game event."""

    game_id: str
    date: date
    season: int
    home_team: str
    away_team: str
    inning: int
    inning_state: str  # top, bottom
    pitcher_id: str | None = None
    pitcher_name: str | None = None
    batter_id: str | None = None
    batter_name: str | None = None
    event_code: str
    event_description: str
    runs_scored: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


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
    attendance: int | None = None
    weather: str | None = None
    wind_direction: str | None = None
    wind_speed: int | None = None
    temperature: int | None = None
