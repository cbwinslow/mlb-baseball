"""
================================================================================
MLB Data Models
Date: 2026-05-09

Pydantic models for MLB-specific types and request/response structures.
================================================================================
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class MLBScheduleRequest(BaseModel):
    """Request model for schedule downloads."""

    season: int = Field(..., ge=1900, le=2100, description="Season year")
    start_season: int | None = Field(
        None, ge=1900, description="Start season for range"
    )
    end_season: int | None = Field(None, ge=1900, description="End season for range")
    team_id: str | None = Field(None, description='Team ID (e.g., "NYY")')
    start_date: date | None = Field(None, description="Start date (ISO format)")
    end_date: date | None = Field(None, description="End date (ISO format)")

    @field_validator("start_season", "end_season")
    @classmethod
    def validate_season_range(cls, v: int | None) -> int | None:
        """Validate season is in reasonable range."""
        if v is not None and (v < 1900 or v > 2100):
            raise ValueError(f"Season {v} out of valid range")
        return v


class MLBGameRequest(BaseModel):
    """Request model for game data download."""

    game_pk: int = Field(..., description="Game ID")
    include_live_feed: bool = Field(True, description="Include live feed data")
    include_boxscore: bool = Field(True, description="Include boxscore")
    include_pbp: bool = Field(True, description="Include play-by-play")


class MLBLiveRequest(BaseModel):
    """Request model for live game polling."""

    game_pk: int = Field(..., description="Game ID")
    poll_interval: int = Field(10, ge=5, le=60, description="Poll interval in seconds")
    max_polls: int | None = Field(None, description="Max number of polls")
    timeout_seconds: int | None = Field(None, description="Polling timeout in seconds")


class MLBGameState(BaseModel):
    """Parsed game state."""

    game_pk: int
    game_date: datetime
    status: str  # Pre-Game, In Progress, Final, Completed Early, etc.
    inning: int | None = None
    inning_state: str | None = None  # top, bottom
    home_team: str
    away_team: str
    home_score: int = 0
    away_score: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class MLBPlay(BaseModel):
    """A single play event."""

    game_pk: int
    play_id: int
    inning: int
    inning_state: str  # top, bottom
    pitcher_id: int | None = None
    pitcher_name: str | None = None
    batter_id: int | None = None
    batter_name: str | None = None
    play_description: str | None = None
    event: str | None = None
    event_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
