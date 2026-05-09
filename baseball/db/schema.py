"""
================================================================================
Database Schema Models
Name: schema.py
Date: 2026-05-09
Script: schema.py
Version: 1.0.0
Log Summary: SQLAlchemy ORM models for all database layers
Description: Core, staging, raw, and bridge table definitions
Change Summary: Initial implementation with full provenance tracking
Inputs: Column definitions, relationships, constraints
Outputs: ORM model classes for all canonical tables
================================================================================
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Player(Base):
    """Core canonical player table."""

    __tablename__ = "players"

    player_id = Column(String(50), primary_key=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    full_name = Column(String(200), nullable=False)
    birth_date = Column(DateTime, nullable=True)
    death_date = Column(DateTime, nullable=True)
    bats = Column(String(1), nullable=True)  # L, R, S
    throws = Column(String(1), nullable=True)  # L, R
    height_inches = Column(Integer, nullable=True)
    weight_lbs = Column(Integer, nullable=True)
    debut_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_players_full_name", "full_name"),
        Index("idx_players_birth_date", "birth_date"),
    )


class Team(Base):
    """Core canonical team table."""

    __tablename__ = "teams"

    team_id = Column(String(50), primary_key=True)
    team_name = Column(String(100), nullable=False)
    location = Column(String(100), nullable=True)
    league = Column(String(2), nullable=True)  # AL, NL
    division = Column(String(50), nullable=True)
    founded_year = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index("idx_teams_league_division", "league", "division"),)


class Park(Base):
    """Core canonical park/venue table."""

    __tablename__ = "parks"

    park_id = Column(String(50), primary_key=True)
    park_name = Column(String(150), nullable=False)
    location = Column(String(150), nullable=True)
    capacity = Column(Integer, nullable=True)
    surface = Column(String(50), nullable=True)  # grass, turf
    opened_year = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index("idx_parks_location", "location"),)


class Game(Base):
    """Core canonical game table."""

    __tablename__ = "games"

    game_id = Column(String(100), primary_key=True)
    game_date = Column(DateTime, nullable=False)
    game_datetime = Column(DateTime, nullable=False)
    season = Column(Integer, nullable=False)
    game_type = Column(String(10), nullable=True)  # R, F, D, L, W, C
    home_team_id = Column(String(50), ForeignKey("teams.team_id"), nullable=False)
    away_team_id = Column(String(50), ForeignKey("teams.team_id"), nullable=False)
    park_id = Column(String(50), ForeignKey("parks.park_id"), nullable=True)
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    status = Column(String(50), nullable=True)  # Scheduled, Pre-Game, In Progress, Final
    inning = Column(Integer, nullable=True)
    inning_state = Column(String(20), nullable=True)  # Top, Bottom
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_games_date", "game_date"),
        Index("idx_games_season", "season"),
        Index("idx_games_home_away", "home_team_id", "away_team_id"),
    )


class Event(Base):
    """Core canonical play-by-play event table."""

    __tablename__ = "events"

    event_id = Column(String(100), primary_key=True)
    game_id = Column(String(100), ForeignKey("games.game_id"), nullable=False)
    inning = Column(Integer, nullable=False)
    inning_topbot = Column(String(1), nullable=False)  # T, B
    batter_id = Column(String(50), ForeignKey("players.player_id"), nullable=True)
    pitcher_id = Column(String(50), ForeignKey("players.player_id"), nullable=True)
    event_type = Column(String(50), nullable=True)
    event_text = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    pitch_count = Column(Integer, nullable=True)
    strike_count = Column(Integer, nullable=True)
    ball_count = Column(Integer, nullable=True)
    outs = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_events_game_id", "game_id"),
        Index("idx_events_inning", "inning", "inning_topbot"),
    )


class Pitch(Base):
    """Core canonical pitch/statcast table."""

    __tablename__ = "pitches"

    pitch_id = Column(String(100), primary_key=True)
    game_id = Column(String(100), ForeignKey("games.game_id"), nullable=False)
    event_id = Column(String(100), ForeignKey("events.event_id"), nullable=True)
    pitcher_id = Column(String(50), ForeignKey("players.player_id"), nullable=True)
    batter_id = Column(String(50), ForeignKey("players.player_id"), nullable=True)
    pitch_type = Column(String(10), nullable=True)
    release_speed = Column(Float, nullable=True)
    release_spin_rate = Column(Float, nullable=True)
    release_extension = Column(Float, nullable=True)
    release_position_x = Column(Float, nullable=True)
    release_position_y = Column(Float, nullable=True)
    release_position_z = Column(Float, nullable=True)
    plate_x = Column(Float, nullable=True)
    plate_z = Column(Float, nullable=True)
    pfx_x = Column(Float, nullable=True)
    pfx_z = Column(Float, nullable=True)
    result = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_pitches_game_id", "game_id"),
        Index("idx_pitches_pitcher_id", "pitcher_id"),
        Index("idx_pitches_batter_id", "batter_id"),
    )


class SourceCrosswalk(Base):
    """Bridge table for source ID mapping."""

    __tablename__ = "source_crosswalk"

    crosswalk_id = Column(String(100), primary_key=True)
    source_name = Column(String(50), nullable=False)  # mlbam, retrosheet, lahman, etc.
    source_id = Column(String(100), nullable=False)
    canonical_type = Column(String(50), nullable=False)  # player, team, game, park
    canonical_id = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "source_name", "source_id", "canonical_type", name="uq_source_canonical"
        ),
        Index("idx_crosswalk_source", "source_name", "source_id"),
        Index("idx_crosswalk_canonical", "canonical_type", "canonical_id"),
    )


class RawPayloadMetadata(Base):
    """Tracks all raw source payloads and ingestion metadata."""

    __tablename__ = "raw_payload_metadata"

    payload_id = Column(String(100), primary_key=True)
    source_name = Column(String(50), nullable=False)
    endpoint = Column(String(255), nullable=False)
    payload_type = Column(String(50), nullable=True)  # game, player, statcast, etc.
    params = Column(Text, nullable=True)  # JSON string of query parameters
    checksum = Column(String(64), nullable=True)  # SHA256 hash of payload
    payload_size_bytes = Column(Integer, nullable=True)
    record_count = Column(Integer, nullable=True)
    retrieved_at = Column(DateTime, nullable=False)
    processing_status = Column(String(50), default="pending")  # pending, processing, ingested, failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_payload_source", "source_name"),
        Index("idx_payload_endpoint", "endpoint"),
        Index("idx_payload_status", "processing_status"),
        Index("idx_payload_retrieved", "retrieved_at"),
    )


class SchemaMigration(Base):
    """Tracks applied database migrations."""

    __tablename__ = "schema_migrations"

    migration_id = Column(String(100), primary_key=True)
    name = Column(String(255), nullable=False)
    applied_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    execution_time_ms = Column(Integer, nullable=True)
    status = Column(String(50), default="success")  # success, failed, rolled_back
    error_message = Column(Text, nullable=True)

    __table_args__ = (Index("idx_migrations_applied_at", "applied_at"),)


class SchemaValidation(Base):
    """Tracks schema validation results."""

    __tablename__ = "schema_validation"

    validation_id = Column(String(100), primary_key=True)
    check_type = Column(String(100), nullable=False)
    object_type = Column(String(100), nullable=False)
    object_name = Column(String(255), nullable=False)
    is_valid = Column(Boolean, nullable=False)
    error_message = Column(Text, nullable=True)
    checked_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_validation_checked_at", "checked_at"),
        Index("idx_validation_status", "is_valid"),
    )
