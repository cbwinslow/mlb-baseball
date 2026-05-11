"""
================================================================================
Statcast/Baseball Savant Source Adapter
Name: statcast.py
Date: 2026-05-11
Script: statcast.py
Version: 1.0.0
Log Summary: Baseball Savant Statcast pitch-by-pitch data client
Description: Scraper for Statcast pitch data from Baseball Savant
Change Summary: Initial implementation with date range support
Inputs: Date range (start_date, end_date), additional filters
Outputs: Statcast pitch-by-pitch data in CSV/JSON format
================================================================================
"""

from datetime import datetime, timedelta
from typing import List, Optional

import httpx

from baseball.core.logging import get_logger

logger = get_logger(__name__)


class StatcastClient:
    """Client for Baseball Savant Statcast pitch data."""

    BASE_URL = "https://baseballsavant.mlb.com"

    def __init__(self, timeout: int = 30):
        """Initialize Statcast client.

        Args:
            timeout: HTTP request timeout in seconds
        """
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)

    def get_statcast(
        self,
        start_date: str,
        end_date: Optional[str] = None,
        pitcher_id: Optional[int] = None,
        batter_id: Optional[int] = None,
        team: Optional[str] = None,
    ) -> List[dict]:
        """Get Statcast data for date range.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD), defaults to start_date
            pitcher_id: Filter by pitcher (optional)
            batter_id: Filter by batter (optional)
            team: Filter by team (optional)

        Returns:
            List of pitch dictionaries
        """
        if end_date is None:
            end_date = start_date

        # Build query parameters
        params = {
            "all": "true",
            "hfabd": "",
            "group_by": "name",
        }

        # Add date filter
        params["min_pitches"] = "0"
        params["csv_down_load"] = "true"
        params["csv_file_name"] = f"statcast_{start_date}_to_{end_date}"

        # Add optional filters
        if pitcher_id:
            params["pitcher_id"] = pitcher_id
        if batter_id:
            params["batter_id"] = batter_id
        if team:
            params["team"] = team

        try:
            url = f"{self.BASE_URL}/csv"
            response = self.client.get(url, params=params)
            response.raise_for_status()
            logger.info(f"Retrieved Statcast data for {start_date} to {end_date}")
            return response.text
        except Exception as e:
            logger.error(f"Failed to retrieve Statcast data: {e}")
            return []

    def close(self) -> None:
        """Close HTTP client."""
        self.client.close()
