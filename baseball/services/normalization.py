"""
================================================================================
Normalization Services
Date: 2026-05-09

Normalize source-specific data into canonical structures.
================================================================================
"""


import pandas as pd

from baseball.core.logging import get_logger


logger = get_logger(__name__)


def normalize_mlb_schedule(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize MLB schedule to canonical format.

    Args:
        df: Raw schedule DataFrame

    Returns:
        Normalized DataFrame
    """
    normalized = df.copy()

    # Rename columns to canonical names
    rename_map = {
        "game_pk": "game_id",
        "home_team": "home_team_name",
        "away_team": "away_team_name",
    }
    normalized = normalized.rename(columns=rename_map)

    # Ensure required columns
    required = {"game_id", "game_date", "season", "status"}
    if not required.issubset(set(normalized.columns)):
        raise ValueError(f"Missing required columns: {required - set(normalized.columns)}")

    logger.info(f"Normalized {len(normalized)} schedule records")
    return normalized


def normalize_retrosheet_events(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize Retrosheet events to canonical format.

    Args:
        df: Raw events DataFrame

    Returns:
        Normalized DataFrame
    """
    normalized = df.copy()

    # TODO: Map Retrosheet-specific fields to canonical names
    logger.info(f"Normalized {len(normalized)} event records")
    return normalized


def normalize_statcast_pitches(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize StatCast pitches to canonical format.

    Args:
        df: Raw pitch DataFrame

    Returns:
        Normalized DataFrame
    """
    normalized = df.copy()

    # StatCast already uses canonical names mostly
    logger.info(f"Normalized {len(normalized)} pitch records")
    return normalized
