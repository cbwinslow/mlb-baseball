"""
================================================================================
Database Models (SQLAlchemy ORM)
Name: models.py
Date: 2026-05-11
Script: models.py
Version: 1.0.0
Log Summary: Comprehensive SQLAlchemy ORM models for all data layers
Description: Core, raw, staging, bridge tables and relationships
Change Summary: Initial implementation with full type hints and constraints
Inputs: PostgreSQL schema definitions
Outputs: SQLAlchemy declarative models with relationships
================================================================================
"""

from datetime import datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Boolean,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


# ==================== CORE CANONICAL TABLES ====================


class Player(Base):
    """Core player dimension."""

    __tablename__ = "player"

    player_id = Column(Integer, primary_key=True)
    player_mlbam_id = Column(Integer, unique=True, nullable=True, index=True)
    player_retrosheet_id = Column(String(20), unique=True, nullable=True, index=True)
    player_lahman_id = Column(String(20), unique=True, nullable=True, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    bats = Column(String(1), nullable=True)  # L, R, S
    throws = Column(String(1), nullable=True)  # L, R
    birth_date = Column(Date, nullable=True)
    death_date = Column(Date, nullable=True)
    debut_date = Column(Date, nullable=True)
    final_game_date = Column(Date, nullable=True)
    height_inches = Column(Integer, nullable=True)
    weight_lbs = Column(Integer, nullable=True)
    position_primary = Column(String(10), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_player_names", "last_name", "first_name"),
        Index("ix_player_debut", "debut_date"),
    )


class Team(Base):
    """Core team dimension."""

    __tablename__ = "team"

    team_id = Column(Integer, primary_key=True)
    team_mlbam_id = Column(Integer, unique=True, nullable=True, index=True)
    team_retrosheet_id = Column(String(5), unique=True, nullable=True, index=True)
    team_lahman_id = Column(String(5), unique=True, nullable=True, index=True)
    franchise_id = Column(String(20), nullable=True)
    team_name = Column(String(50), nullable=False, unique=True)
    team_abbr = Column(String(3), nullable=False, unique=True, index=True)
    league = Column(String(2), nullable=False)  # AL, NL
    division = Column(String(10), nullable=True)
    location = Column(String(100), nullable=True)
    founded_year = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_team_league_division", "league", "division"),
    )


class Park(Base):
    """Core park/stadium dimension."""

    __tablename__ = "park"

    park_id = Column(Integer, primary_key=True)
    park_mlbam_id = Column(Integer, unique=True, nullable=True, index=True)
    park_retrosheet_id = Column(String(10), unique=True, nullable=True, index=True)
    park_name = Column(String(100), nullable=False, unique=True)
    park_alias = Column(String(100), nullable=True)
    city = Column(String(50), nullable=True)
    state = Column(String(2), nullable=True)
    country = Column(String(50), nullable=True, default="USA")
    home_team_id = Column(Integer, ForeignKey("team.team_id"), nullable=True)
    opened_year = Column(Integer, nullable=True)
    closed_year = Column(Integer, nullable=True)
    capacity = Column(Integer, nullable=True)
    surface_type = Column(String(50), nullable=True)  # grass, artificial, turf
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    home_team = relationship("Team")


class Game(Base):
    """Core game fact table."""

    __tablename__ = "game"

    game_id = Column(Integer, primary_key=True)
    game_mlbam_id = Column(String(50), unique=True, nullable=True, index=True)
    game_retrosheet_id = Column(String(50), unique=True, nullable=True, index=True)
    game_datetime_utc = Column(DateTime, nullable=False, index=True)
    game_date = Column(Date, nullable=False, index=True)
    season = Column(Integer, nullable=False, index=True)
    game_number = Column(Integer, nullable=True)  # 1 for first game, 2 for doubleheader
    game_type = Column(String(10), nullable=True)  # S (season), P (playoff), etc.
    home_team_id = Column(Integer, ForeignKey("team.team_id"), nullable=False)
    away_team_id = Column(Integer, ForeignKey("team.team_id"), nullable=False)
    park_id = Column(Integer, ForeignKey("park.park_id"), nullable=True)
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    game_status = Column(String(20), nullable=True)  # Final, Ongoing, Postponed, etc.
    innings_played = Column(Integer, nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    attendance = Column(Integer, nullable=True)
    weather_condition = Column(String(50), nullable=True)
    weather_temp_f = Column(Integer, nullable=True)
    weather_wind_mph = Column(Numeric(5, 1), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    home_team = relationship("Team", foreign_keys=[home_team_id])
    away_team = relationship("Team", foreign_keys=[away_team_id])
    park = relationship("Park")

    __table_args__ = (
        Index("ix_game_season_date", "season", "game_date"),
        Index("ix_game_teams", "home_team_id", "away_team_id"),
    )


class PlayByPlay(Base):
    """Core play-by-play events (retrosheet)."""

    __tablename__ = "play_by_play"

    pbp_id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("game.game_id"), nullable=False, index=True)
    inning = Column(Integer, nullable=False)
    half_inning = Column(String(3), nullable=False)  # top, bot
    batter_id = Column(Integer, ForeignKey("player.player_id"), nullable=True)
    pitcher_id = Column(Integer, ForeignKey("player.player_id"), nullable=True)
    sequence_number = Column(Integer, nullable=False)  # Order in inning
    balls = Column(Integer, nullable=True)
    strikes = Column(Integer, nullable=True)
    outs_at_start = Column(Integer, nullable=True)
    pitch_count = Column(Integer, nullable=True)
    event_type = Column(String(100), nullable=True)
    event_code = Column(String(10), nullable=True)  # Retrosheet event code
    runs_scored = Column(Integer, nullable=True, default=0)
    rbis = Column(Integer, nullable=True, default=0)
    home_score_after = Column(Integer, nullable=True)
    away_score_after = Column(Integer, nullable=True)
    raw_event_description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    game = relationship("Game")
    batter = relationship("Player", foreign_keys=[batter_id])
    pitcher = relationship("Player", foreign_keys=[pitcher_id])

    __table_args__ = (
        Index("ix_pbp_game_inning", "game_id", "inning", "half_inning"),
    )


class Pitch(Base):
    """Core pitch data (Statcast/Savant)."""

    __tablename__ = "pitch"

    pitch_id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("game.game_id"), nullable=False, index=True)
    play_id = Column(String(50), nullable=True)  # Statcast play ID
    pitcher_id = Column(Integer, ForeignKey("player.player_id"), nullable=True)
    batter_id = Column(Integer, ForeignKey("player.player_id"), nullable=True)
    pitch_type = Column(String(10), nullable=True)  # FF, CH, CU, etc.
    release_speed_mph = Column(Numeric(6, 2), nullable=True)
    spin_rate_rpm = Column(Integer, nullable=True)
    spin_axis = Column(Numeric(6, 2), nullable=True)
    ivb = Column(Numeric(6, 3), nullable=True)  # induced vertical break
    hb = Column(Numeric(6, 3), nullable=True)  # horizontal break
    px = Column(Numeric(6, 3), nullable=True)  # plate x location
    pz = Column(Numeric(6, 3), nullable=True)  # plate z location
    vx0 = Column(Numeric(6, 3), nullable=True)  # initial velocity x
    vy0 = Column(Numeric(6, 3), nullable=True)  # initial velocity y
    vz0 = Column(Numeric(6, 3), nullable=True)  # initial velocity z
    ax = Column(Numeric(6, 3), nullable=True)  # acceleration x
    ay = Column(Numeric(6, 3), nullable=True)  # acceleration y
    az = Column(Numeric(6, 3), nullable=True)  # acceleration z
    pfx_x = Column(Numeric(6, 3), nullable=True)  # break x
    pfx_z = Column(Numeric(6, 3), nullable=True)  # break z
    description = Column(String(100), nullable=True)  # Called strike, foul, etc.
    result = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    game = relationship("Game")
    pitcher = relationship("Player", foreign_keys=[pitcher_id])
    batter = relationship("Player", foreign_keys=[batter_id])

    __table_args__ = (
        Index("ix_pitch_game", "game_id"),
        Index("ix_pitch_pitcher", "pitcher_id"),
        Index("ix_pitch_batter", "batter_id"),
    )


class PlayerSeason(Base):
    """Player season statistics aggregate."""

    __tablename__ = "player_season"

    player_season_id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("player.player_id"), nullable=False)
    season = Column(Integer, nullable=False)
    source = Column(String(20), nullable=False)  # mlb, retrosheet, fangraphs
    games_played = Column(Integer, nullable=True)
    plate_appearances = Column(Integer, nullable=True)
    at_bats = Column(Integer, nullable=True)
    hits = Column(Integer, nullable=True)
    doubles = Column(Integer, nullable=True)
    triples = Column(Integer, nullable=True)
    home_runs = Column(Integer, nullable=True)
    rbis = Column(Integer, nullable=True)
    runs = Column(Integer, nullable=True)
    walks = Column(Integer, nullable=True)
    strikeouts = Column(Integer, nullable=True)
    batting_avg = Column(Numeric(5, 3), nullable=True)
    on_base_pct = Column(Numeric(5, 3), nullable=True)
    slugging_pct = Column(Numeric(5, 3), nullable=True)
    ops = Column(Numeric(5, 3), nullable=True)
    war = Column(Numeric(6, 2), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    player = relationship("Player")

    __table_args__ = (
        UniqueConstraint("player_id", "season", "source", name="uq_player_season_source"),
        Index("ix_player_season", "season", "player_id"),
    )


class PitcherSeason(Base):
    """Pitcher season statistics aggregate."""

    __tablename__ = "pitcher_season"

    pitcher_season_id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("player.player_id"), nullable=False)
    season = Column(Integer, nullable=False)
    source = Column(String(20), nullable=False)
    team_id = Column(Integer, ForeignKey("team.team_id"), nullable=True)
    games = Column(Integer, nullable=True)
    games_started = Column(Integer, nullable=True)
    innings_pitched = Column(Numeric(6, 1), nullable=True)
    wins = Column(Integer, nullable=True)
    losses = Column(Integer, nullable=True)
    saves = Column(Integer, nullable=True)
    earned_run_avg = Column(Numeric(5, 2), nullable=True)
    strikeouts = Column(Integer, nullable=True)
    walks = Column(Integer, nullable=True)
    hits_allowed = Column(Integer, nullable=True)
    home_runs_allowed = Column(Integer, nullable=True)
    whip = Column(Numeric(5, 2), nullable=True)
    fip = Column(Numeric(5, 2), nullable=True)
    war = Column(Numeric(6, 2), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    player = relationship("Player")
    team = relationship("Team")

    __table_args__ = (
        UniqueConstraint("player_id", "season", "source", name="uq_pitcher_season_source"),
        Index("ix_pitcher_season", "season", "player_id"),
    )


class Schedule(Base):
    """Game schedule (future and past)."""

    __tablename__ = "schedule"

    schedule_id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey("game.game_id"), nullable=True, unique=True)
    game_datetime_utc = Column(DateTime, nullable=False, index=True)
    game_date = Column(Date, nullable=False, index=True)
    season = Column(Integer, nullable=False, index=True)
    home_team_id = Column(Integer, ForeignKey("team.team_id"), nullable=False)
    away_team_id = Column(Integer, ForeignKey("team.team_id"), nullable=False)
    park_id = Column(Integer, ForeignKey("park.park_id"), nullable=True)
    game_status = Column(String(20), nullable=True)  # Scheduled, Completed, Postponed
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    game = relationship("Game")
    home_team = relationship("Team", foreign_keys=[home_team_id])
    away_team = relationship("Team", foreign_keys=[away_team_id])
    park = relationship("Park")

    __table_args__ = (
        Index("ix_schedule_season_date", "season", "game_date"),
    )


# ==================== RAW SOURCE TABLES ====================


class RawMlbstatsapi(Base):
    """Raw MLB StatsAPI payload."""

    __tablename__ = "raw_mlbstatsapi"

    raw_id = Column(Integer, primary_key=True)
    endpoint = Column(String(200), nullable=False)  # /game/{id}, /people/{id}, etc.
    resource_id = Column(String(100), nullable=True, index=True)  # game_pk, player_id, etc.
    payload = Column(Text, nullable=False)  # JSON
    checksum = Column(String(64), nullable=True, unique=True)  # SHA256 of payload
    retrieved_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_raw_mlb_endpoint_id", "endpoint", "resource_id"),
        {'schema': 'raw'}
    )


class RawRetrosheet(Base):
    """Raw Retrosheet data file payload."""

    __tablename__ = "raw_retrosheet"

    raw_id = Column(Integer, primary_key=True)
    file_type = Column(String(50), nullable=False)  # event, roster, schedule
    season = Column(Integer, nullable=False, index=True)
    game_date = Column(Date, nullable=True)
    game_id = Column(String(50), nullable=True, index=True)
    file_name = Column(String(200), nullable=False)
    payload = Column(Text, nullable=False)
    checksum = Column(String(64), nullable=True, unique=True)  # SHA256 of payload
    source_url = Column(String(500), nullable=True)
    retrieved_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_raw_retrosheet_season_type", "season", "file_type"),
        {'schema': 'raw'}
    )


class RawStatcast(Base):
    """Raw Statcast/Baseball Savant payload."""

    __tablename__ = "raw_statcast"

    raw_id = Column(Integer, primary_key=True)
    game_date = Column(Date, nullable=False, index=True)
    season = Column(Integer, nullable=False, index=True)
    game_id = Column(String(50), nullable=True, index=True)
    play_id = Column(String(50), nullable=True, unique=True)  # Statcast ID
    payload = Column(Text, nullable=False)  # JSON
    checksum = Column(String(64), nullable=True, unique=True)
    retrieved_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_raw_statcast_game", "game_date", "game_id"),
        {'schema': 'raw'}
    )


class RawFangraphs(Base):
    """Raw FanGraphs data payload."""

    __tablename__ = "raw_fangraphs"

    raw_id = Column(Integer, primary_key=True)
    data_type = Column(String(50), nullable=False)  # batting, pitching, fielding
    season = Column(Integer, nullable=False, index=True)
    resource_id = Column(String(100), nullable=True, index=True)  # player_id
    payload = Column(Text, nullable=False)
    checksum = Column(String(64), nullable=True, unique=True)
    retrieved_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_raw_fangraphs_season_type", "season", "data_type"),
        {'schema': 'raw'}
    )


class RawEspn(Base):
    """Raw ESPN data payload."""

    __tablename__ = "raw_espn_events"

    raw_id = Column(Integer, primary_key=True)
    event_id = Column(String(100), nullable=False, unique=True, index=True)
    competition_id = Column(String(100), nullable=True, index=True)
    season = Column(Integer, nullable=True, index=True)
    game_date = Column(Date, nullable=True, index=True)
    payload = Column(Text, nullable=False)  # JSON
    checksum = Column(String(64), nullable=True, unique=True)  # SHA256 of payload
    retrieved_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_raw_espn_event_date", "event_id", "game_date"),
        {'schema': 'raw'}
    )


class RawEspnCompetitions(Base):
    """Raw ESPN competitions data."""

    __tablename__ = "raw_espn_competitions"

    raw_id = Column(Integer, primary_key=True)
    competition_id = Column(String(100), nullable=False, unique=True, index=True)
    event_id = Column(String(100), nullable=False, index=True)
    name = Column(String(200), nullable=True)
    date = Column(Date, nullable=True)
    venue_id = Column(String(100), nullable=True)
    venue_name = Column(String(200), nullable=True)
    payload = Column(Text, nullable=False)  # JSON
    checksum = Column(String(64), nullable=True, unique=True)
    retrieved_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_raw_espn_competition_event", "competition_id", "event_id"),
        {'schema': 'raw'}
    )


class RawEspnTeams(Base):
    """Raw ESPN teams data."""

    __tablename__ = "raw_espn_teams"

    raw_id = Column(Integer, primary_key=True)
    team_id = Column(String(100), nullable=False, index=True)
    competition_id = Column(String(100), nullable=False, index=True)
    event_id = Column(String(100), nullable=False, index=True)
    home_away = Column(String(10), nullable=True)  # home/away
    winner = Column(Boolean, nullable=True)
    score = Column(Integer, nullable=True)
    team_uid = Column(String(100), nullable=True)
    team_slug = Column(String(100), nullable=True)
    team_location = Column(String(200), nullable=True)
    team_name = Column(String(200), nullable=True)
    team_abbreviation = Column(String(20), nullable=True)
    team_display_name = Column(String(200), nullable=True)
    team_short_display_name = Column(String(100), nullable=True)
    source_url = Column(Text, nullable=True)
    payload = Column(Text, nullable=False)  # JSON
    checksum = Column(String(64), nullable=True, unique=True)
    retrieved_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_raw_espn_team_competition", "team_id", "competition_id"),
        Index("ix_raw_espn_team_event", "team_id", "event_id"),
        {'schema': 'raw'}
    )


class RawEspnVenues(Base):
    """Raw ESPN venues data."""

    __tablename__ = "raw_espn_venues"

    raw_id = Column(Integer, primary_key=True)
    venue_id = Column(String(100), nullable=False, unique=True, index=True)
    venue_name = Column(String(200), nullable=True)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    state = Column(String(50), nullable=True)
    country = Column(String(100), nullable=True)
    capacity = Column(Integer, nullable=True)
    indoor = Column(Boolean, nullable=True)
    payload = Column(Text, nullable=False)  # JSON
    checksum = Column(String(64), nullable=True, unique=True)
    retrieved_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        {'schema': 'raw'}
    )


class RawEspnBroadcasts(Base):
    """Raw ESPN broadcasts data."""

    __tablename__ = "raw_espn_broadcasts"

    raw_id = Column(Integer, primary_key=True)
    broadcast_id = Column(String(100), nullable=False, unique=True, index=True)
    event_id = Column(String(100), nullable=False, index=True)
    competition_id = Column(String(100), nullable=True, index=True)
    market = Column(String(100), nullable=True)
    language = Column(String(50), nullable=True)
    type = Column(String(50), nullable=True)  # TV, streaming, radio, etc.
    names = Column(Text, nullable=True)  # JSON array of broadcaster names
    payload = Column(Text, nullable=False)  # JSON
    checksum = Column(String(64), nullable=True, unique=True)
    retrieved_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_raw_espn_broadcast_event", "broadcast_id", "event_id"),
        {'schema': 'raw'}
    )


class RawEspnOdds(Base):
    """Raw ESPN odds data."""

    __tablename__ = "raw_espn_odds"

    raw_id = Column(Integer, primary_key=True)
    odds_id = Column(String(100), nullable=False, unique=True, index=True)
    event_id = Column(String(100), nullable=False, index=True)
    competition_id = Column(String(100), nullable=True, index=True)
    provider = Column(String(100), nullable=True)  # e.g., "consensus", "draftkings"
    home_team_moneyline = Column(Integer, nullable=True)
    away_team_moneyline = Column(Integer, nullable=True)
    home_team_spread = Column(Numeric(5, 2), nullable=True)
    away_team_spread = Column(Numeric(5, 2), nullable=True)
    spread_points = Column(Numeric(5, 2), nullable=True)
    over_under = Column(Numeric(5, 2), nullable=True)
    over_odds = Column(Integer, nullable=True)
    under_odds = Column(Integer, nullable=True)
    payload = Column(Text, nullable=False)  # JSON
    checksum = Column(String(64), nullable=True, unique=True)
    retrieved_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_raw_espn_odds_event", "odds_id", "event_id"),
        {'schema': 'raw'}
    )


class RawWeatherStations(Base):
    """Raw weather stations data."""

    __tablename__ = "raw_weather_stations"

    raw_id = Column(Integer, primary_key=True)
    station_id = Column(String(100), nullable=False, unique=True, index=True)
    station_name = Column(String(200), nullable=True)
    elevation = Column(Integer, nullable=True)
    latitude = Column(Numeric(10, 6), nullable=True)
    longitude = Column(Numeric(10, 6), nullable=True)
    timezone = Column(String(100), nullable=True)
    payload = Column(Text, nullable=False)  # JSON
    checksum = Column(String(64), nullable=True, unique=True)
    retrieved_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        {'schema': 'raw'}
    )


class RawWeatherForecasts(Base):
    """Raw weather forecasts data."""

    __tablename__ = "raw_weather_forecasts"

    raw_id = Column(Integer, primary_key=True)
    forecast_id = Column(String(100), nullable=False, unique=True, index=True)
    station_id = Column(String(100), nullable=False, index=True)
    issuance_time = Column(DateTime, nullable=True, index=True)
    valid_time = Column(DateTime, nullable=True, index=True)
    payload = Column(Text, nullable=False)  # JSON
    checksum = Column(String(64), nullable=True, unique=True)
    retrieved_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_raw_weather_forecast_station", "forecast_id", "station_id"),
        {'schema': 'raw'}
    )


class RawWeatherPeriods(Base):
    """Raw weather forecast periods data."""

    __tablename__ = "raw_weather_periods"

    raw_id = Column(Integer, primary_key=True)
    period_id = Column(String(100), nullable=False, unique=True, index=True)
    forecast_id = Column(String(100), nullable=False, index=True)
    station_id = Column(String(100), nullable=False, index=True)
    start_time = Column(DateTime, nullable=True, index=True)
    end_time = Column(DateTime, nullable=True, index=True)
    temperature = Column(Integer, nullable=True)
    temperature_unit = Column(String(20), nullable=True)  # F, C
    temperature_trend = Column(String(50), nullable=True)  # rising, falling, steady
    probability_of_precipitation = Column(Integer, nullable=True)  # percentage
    precipitation_amount = Column(Numeric(5, 2), nullable=True)
    precipitation_amount_unit = Column(String(20), nullable=True)  # in, mm
    precipitation_type = Column(String(50), nullable=True)  # rain, snow, mixed
    wind_speed = Column(Integer, nullable=True)
    wind_speed_unit = Column(String(20), nullable=True)  # mph, kph
    wind_direction = Column(String(10), nullable=True)  # N, NE, E, SE, S, SW, W, NW
    wind_direction_degrees = Column(Integer, nullable=True)
    relative_humidity = Column(Integer, nullable=True)  # percentage
    dewpoint = Column(Integer, nullable=True)
    dewpoint_unit = Column(String(20), nullable=True)  # F, C
    pressure = Column(Numeric(6, 2), nullable=True)
    pressure_unit = Column(String(20), nullable=True)  # mb, hPa, inHg
    visibility = Column(Numeric(6, 2), nullable=True)
    visibility_unit = Column(String(20), nullable=True)  # mi, km
    sky_cover = Column(Integer, nullable=True)  # percentage
    sky_cover_text = Column(String(100), nullable=True)  # clear, few, scattered, broken, overcast
    ceiling = Column(Integer, nullable=True)
    ceiling_unit = Column(String(20), nullable=True)  # ft, m
    ceiling_aggravation = Column(String(100), nullable=True)  # none, obscuration, partial, total
    payload = Column(Text, nullable=False)  # JSON
    checksum = Column(String(64), nullable=True, unique=True)
    retrieved_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_raw_weather_period_forecast", "period_id", "forecast_id"),
        Index("ix_raw_weather_period_station", "period_id", "station_id"),
        {'schema': 'raw'}
    )


# ==================== BRIDGE/CROSSWALK TABLES ====================


class PlayerXwalk(Base):
    """Player ID crosswalk across all sources."""

    __tablename__ = "player_xwalk"

    xwalk_id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("player.player_id"), nullable=False, index=True)
    mlbam_id = Column(Integer, nullable=True, unique=True)
    retrosheet_id = Column(String(20), nullable=True, unique=True)
    lahman_id = Column(String(20), nullable=True, unique=True)
    fangraphs_id = Column(Integer, nullable=True, unique=True)
    bbref_id = Column(String(50), nullable=True, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    player = relationship("Player")


class TeamXwalk(Base):
    """Team ID crosswalk across all sources."""

    __tablename__ = "team_xwalk"

    xwalk_id = Column(Integer, primary_key=True)
    team_id = Column(Integer, ForeignKey("team.team_id"), nullable=False, index=True)
    mlbam_id = Column(Integer, nullable=True, unique=True)
    retrosheet_id = Column(String(5), nullable=True, unique=True)
    lahman_id = Column(String(5), nullable=True, unique=True)
    bbref_id = Column(String(20), nullable=True, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    team = relationship("Team")


class ParkXwalk(Base):
    """Park ID crosswalk across all sources."""

    __tablename__ = "park_xwalk"

    xwalk_id = Column(Integer, primary_key=True)
    park_id = Column(Integer, ForeignKey("park.park_id"), nullable=False, index=True)
    mlbam_id = Column(Integer, nullable=True, unique=True)
    retrosheet_id = Column(String(10), nullable=True, unique=True)
    bbref_id = Column(String(50), nullable=True, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    park = relationship("Park")


# ==================== METADATA TABLES ====================


class IngestLog(Base):
    """Track all ingestion operations."""

    __tablename__ = "ingest_log"

    log_id = Column(Integer, primary_key=True)
    source = Column(String(50), nullable=False)  # mlbstatsapi, retrosheet, statcast, etc.
    endpoint_or_file = Column(String(200), nullable=False)
    season = Column(Integer, nullable=True)
    rows_processed = Column(Integer, nullable=False, default=0)
    rows_inserted = Column(Integer, nullable=False, default=0)
    rows_updated = Column(Integer, nullable=False, default=0)
    rows_skipped = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False)  # success, failed, partial
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_ingest_log_source_date", "source", "started_at"),
    )


class ValidationLog(Base):
    """Track data validation runs."""

    __tablename__ = "validation_log"

    log_id = Column(Integer, primary_key=True)
    check_name = Column(String(100), nullable=False)
    table_name = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False)  # passed, failed, warning
    row_count = Column(Integer, nullable=True)
    issue_count = Column(Integer, nullable=False, default=0)
    issue_description = Column(Text, nullable=True)
    checked_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_validation_check_date", "check_name", "checked_at"),
    )
