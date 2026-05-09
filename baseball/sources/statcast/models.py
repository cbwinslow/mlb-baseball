"""
================================================================================
StatCast Data Models
Date: 2026-05-09

Pydantic models for StatCast pitch-level data.
================================================================================
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class StatcastRequest(BaseModel):
    """Request model for StatCast data download."""

    season: int | None = Field(None, ge=2015, description="Single season")
    start_season: int | None = Field(None, ge=2015, description="Start season")
    end_season: int | None = Field(None, ge=2015, description="End season")
    start_date: date | None = Field(None, description="Start date")
    end_date: date | None = Field(None, description="End date")
    pitcher_id: int | None = Field(None, description="Pitcher MLBAM ID")
    batter_id: int | None = Field(None, description="Batter MLBAM ID")
    teams: list[str] | None = Field(None, description="Team abbreviations")


class StatcastPitch(BaseModel):
    """A single pitch from StatCast."""

    game_pk: int
    game_date: date
    inning: int
    inning_topbot: str  # Top or Bot
    pitcher_id: int | None = None
    pitcher_name: str | None = None
    batter_id: int | None = None
    batter_name: str | None = None
    pitch_type: str | None = None
    pitch_name: str | None = None
    release_speed: float | None = None
    release_extension: float | None = None
    pfx_x: float | None = None  # Horizontal break
    pfx_z: float | None = None  # Vertical break
    plate_x: float | None = None  # X location at plate
    plate_z: float | None = None  # Z location at plate
    events: str | None = None
    description: str | None = None
    launch_speed: float | None = None
    launch_angle: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
