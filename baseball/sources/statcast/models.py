
"""
================================================================================
StatCast Data Models
Date: 2026-05-09

Pydantic models for StatCast pitch-level data.
================================================================================
"""

from datetime import date, datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class StatcastRequest(BaseModel):
    """Request model for StatCast data download."""

    season: Optional[int] = Field(None, ge=2015, description='Single season')
    start_season: Optional[int] = Field(None, ge=2015, description='Start season')
    end_season: Optional[int] = Field(None, ge=2015, description='End season')
    start_date: Optional[date] = Field(None, description='Start date')
    end_date: Optional[date] = Field(None, description='End date')
    pitcher_id: Optional[int] = Field(None, description='Pitcher MLBAM ID')
    batter_id: Optional[int] = Field(None, description='Batter MLBAM ID')
    teams: Optional[list[str]] = Field(None, description='Team abbreviations')


class StatcastPitch(BaseModel):
    """A single pitch from StatCast."""

    game_pk: int
    game_date: date
    inning: int
    inning_topbot: str  # Top or Bot
    pitcher_id: Optional[int] = None
    pitcher_name: Optional[str] = None
    batter_id: Optional[int] = None
    batter_name: Optional[str] = None
    pitch_type: Optional[str] = None
    pitch_name: Optional[str] = None
    release_speed: Optional[float] = None
    release_extension: Optional[float] = None
    pfx_x: Optional[float] = None  # Horizontal break
    pfx_z: Optional[float] = None  # Vertical break
    plate_x: Optional[float] = None  # X location at plate
    plate_z: Optional[float] = None  # Z location at plate
    events: Optional[str] = None
    description: Optional[str] = None
    launch_speed: Optional[float] = None
    launch_angle: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)