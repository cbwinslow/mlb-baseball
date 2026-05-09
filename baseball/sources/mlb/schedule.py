"""
================================================================================
MLB Schedule Planning
Date: 2026-05-09

Schedule discovery and polling plan generation.
================================================================================
"""

from datetime import date, timedelta

from baseball.core.logging import get_logger
from baseball.sources.mlb.client import MLBClient

logger = get_logger(__name__)


class MLBSchedulePlanner:
    """Plan and discover MLB game schedules."""

    def __init__(self):
        """Initialize planner."""
        self.client = MLBClient()

    def get_games_for_date(self, game_date: date) -> list[int]:
        """Get all game PKs for a specific date.

        Args:
            game_date: Date to get games for

        Returns:
            List of game PKs
        """
        logger.info(f"Fetching games for {game_date}")

        # Get season from date
        season = game_date.year

        # Fetch schedule for season
        data = self.client.get_schedule(season=season)

        game_pks = []
        target_date_str = game_date.isoformat()

        for date_block in data.get("dates", []):
            if date_block["date"] == target_date_str:
                for game in date_block.get("games", []):
                    game_pks.append(game["gamePk"])

        logger.info(f"Found {len(game_pks)} games for {game_date}")
        return game_pks

    def get_games_in_range(
        self,
        start_date: date,
        end_date: date,
    ) -> list[int]:
        """Get all game PKs in a date range.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List of game PKs
        """
        game_pks = []
        current = start_date

        while current <= end_date:
            game_pks.extend(self.get_games_for_date(current))
            current += timedelta(days=1)

        return game_pks

    def get_todays_games(self) -> list[int]:
        """Get today's games.

        Returns:
            List of game PKs
        """
        today = date.today()
        return self.get_games_for_date(today)
