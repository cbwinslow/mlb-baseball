"""
================================================================================
MLB StatsAPI Source Adapter
Name: mlbstatsapi.py
Date: 2026-05-11
Script: mlbstatsapi.py
Version: 1.0.0
Log Summary: MLB StatsAPI client and endpoint definitions
Description: Direct client for MLB's official StatsAPI with full field preservation
Change Summary: Initial implementation with endpoint inventory
Inputs: API parameters (season, game_pk, player_id)
Outputs: Raw API responses, parsed game/player data
================================================================================
"""

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

from baseball.core.logging import get_logger

logger = get_logger(__name__)


class MLBStatsAPIClient:
    """Direct client for MLB StatsAPI."""

    BASE_URL = "https://statsapi.mlb.com/api/v1"

    def __init__(self, timeout: int = 30):
        """Initialize MLB StatsAPI client.

        Args:
            timeout: HTTP request timeout in seconds
        """
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)

    def get_game(self, game_pk: int) -> Dict[str, Any]:
        """Get game details.

        Args:
            game_pk: Game primary key from MLB

        Returns:
            Game data dictionary
        """
        url = f"{self.BASE_URL}/game/{game_pk}"
        response = self.client.get(url)
        response.raise_for_status()
        return response.json()

    def get_games_by_date(
        self, game_date: str, limit: int = 200
    ) -> List[Dict[str, Any]]:
        """Get all games for a specific date.

        Args:
            game_date: Date in YYYY-MM-DD format
            limit: Max number of games to return

        Returns:
            List of game data dictionaries
        """
        url = f"{self.BASE_URL}/schedule"
        params = {"date": game_date, "limit": limit}
        response = self.client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("dates", [{}])[0].get("games", [])

    def get_season_games(
        self, season: int, limit: int = 200
    ) -> List[Dict[str, Any]]:
        """Get all games for a season.

        Args:
            season: MLB season year
            limit: Max games per request

        Returns:
            List of game data dictionaries
        """
        url = f"{self.BASE_URL}/schedule"
        params = {"season": season, "limit": limit}
        response = self.client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        games = []
        for date_obj in data.get("dates", []):
            games.extend(date_obj.get("games", []))
        return games

    def get_player(self, player_id: int) -> Dict[str, Any]:
        """Get player information.

        Args:
            player_id: MLB player ID

        Returns:
            Player data dictionary
        """
        url = f"{self.BASE_URL}/people/{player_id}"
        response = self.client.get(url)
        response.raise_for_status()
        data = response.json()
        return data.get("people", [{}])[0]

    def get_team(
        self, team_id: int, season: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get team information.

        Args:
            team_id: MLB team ID
            season: Specific season (optional)

        Returns:
            Team data dictionary
        """
        url = f"{self.BASE_URL}/teams/{team_id}"
        params = {}
        if season:
            params["season"] = season
        response = self.client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("teams", [{}])[0]

    def get_season_stats(
        self, player_id: int, season: int, stat_type: str = "season"
    ) -> List[Dict[str, Any]]:
        """Get player season statistics.

        Args:
            player_id: MLB player ID
            season: Season year
            stat_type: Type of stats (season, career, etc.)

        Returns:
            List of stat dictionaries
        """
        url = f"{self.BASE_URL}/people/{player_id}/stat"
        params = {"group": "hitting,pitching,fielding", "type": stat_type}
        response = self.client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("stats", [])

    def close(self) -> None:
        """Close HTTP client."""
        self.client.close()
