"""
================================================================================
MLB API Endpoints
Date: 2026-05-09

Endpoint definitions and URL builders for MLB Stats API.
================================================================================
"""

from enum import Enum


class MLBEndpoint(str, Enum):
    """MLB API endpoints."""

    SCHEDULE = "/schedule"
    GAME_FEED = "/games/{game_pk}/feed/live"
    BOXSCORE = "/games/{game_pk}/boxscore"
    PLAYBYPLAY = "/games/{game_pk}/playByPlay"
    PERSON = "/people/{person_id}"
    PERSON_STATS = "/people/{person_id}/stats"
    STANDINGS = "/standings"
    TEAMS = "/teams"
    VENUES = "/venues"


class MLBEndpointBuilder:
    """Build MLB API endpoint URLs."""

    BASE_URL = "https://statsapi.mlb.com/api/v1"

    @classmethod
    def schedule_url(cls) -> str:
        """Get schedule endpoint URL."""
        return f"{cls.BASE_URL}{MLBEndpoint.SCHEDULE.value}"

    @classmethod
    def game_feed_url(cls, game_pk: int) -> str:
        """Get game feed endpoint URL.

        Args:
            game_pk: Game ID

        Returns:
            Full URL
        """
        path = MLBEndpoint.GAME_FEED.value.format(game_pk=game_pk)
        return f"{cls.BASE_URL}{path}"

    @classmethod
    def boxscore_url(cls, game_pk: int) -> str:
        """Get boxscore endpoint URL.

        Args:
            game_pk: Game ID

        Returns:
            Full URL
        """
        path = MLBEndpoint.BOXSCORE.value.format(game_pk=game_pk)
        return f"{cls.BASE_URL}{path}"

    @classmethod
    def playbyplay_url(cls, game_pk: int) -> str:
        """Get play-by-play endpoint URL.

        Args:
            game_pk: Game ID

        Returns:
            Full URL
        """
        path = MLBEndpoint.PLAYBYPLAY.value.format(game_pk=game_pk)
        return f"{cls.BASE_URL}{path}"

    @classmethod
    def person_stats_url(cls, person_id: int) -> str:
        """Get person stats endpoint URL.

        Args:
            person_id: Person ID

        Returns:
            Full URL
        """
        path = MLBEndpoint.PERSON_STATS.value.format(person_id=person_id)
        return f"{cls.BASE_URL}{path}"
