
"""
================================================================================
MLB API Client
Date: 2026-05-09

Low-level HTTP client for MLB Stats API with retries and rate limiting.
================================================================================
"""

import time
from typing import Any, Dict, Optional

import httpx

from baseball.core.logging import get_logger
from baseball.sources.common.http import create_http_client
from baseball.sources.common.retries import retry_on_http_errors
from baseball.sources.mlb.endpoints import MLBEndpointBuilder
from baseball.sources.mlb.params import MLBParamTransformer


logger = get_logger(__name__)


class MLBClient:
    """MLB Stats API client."""

    DEFAULT_RATE_LIMIT = 0.5  # Seconds between requests
    DEFAULT_TIMEOUT = 30

    def __init__(
        self,
        rate_limit: float = DEFAULT_RATE_LIMIT,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """Initialize MLB client.

        Args:
            rate_limit: Minimum seconds between requests
            timeout: Request timeout in seconds
        """
        self.rate_limit = rate_limit
        self.timeout = timeout
        self.client = create_http_client(timeout=timeout)
        self._last_request_time = 0.0

    def _apply_rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)

        self._last_request_time = time.time()

    @retry_on_http_errors(max_attempts=3)
    def _request(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make HTTP request with retry logic.

        Args:
            url: Endpoint URL
            params: Query parameters

        Returns:
            JSON response

        Raises:
            httpx.HTTPError: On HTTP errors after retries
        """
        self._apply_rate_limit()

        logger.debug(f'GET {url} with params {params}')

        response = self.client.get(url, params=params)
        response.raise_for_status()

        return response.json()

    def get_schedule(
        self,
        season: Optional[int] = None,
        team_id: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Get schedule data.

        Args:
            season: Season year
            team_id: Team ID
            **kwargs: Additional parameters

        Returns:
            Schedule JSON
        """
        url = MLBEndpointBuilder.schedule_url()
        params = MLBParamTransformer.schedule_params(
            season=season,
            team_id=team_id,
        )

        return self._request(url, params)

    def get_game_feed(self, game_pk: int) -> Dict[str, Any]:
        """Get live game feed.

        Args:
            game_pk: Game ID

        Returns:
            Game feed JSON
        """
        url = MLBEndpointBuilder.game_feed_url(game_pk)
        return self._request(url)

    def get_boxscore(self, game_pk: int) -> Dict[str, Any]:
        """Get game boxscore.

        Args:
            game_pk: Game ID

        Returns:
            Boxscore JSON
        """
        url = MLBEndpointBuilder.boxscore_url(game_pk)
        return self._request(url)

    def get_playbyplay(self, game_pk: int) -> Dict[str, Any]:
        """Get play-by-play data.

        Args:
            game_pk: Game ID

        Returns:
            Play-by-play JSON
        """
        url = MLBEndpointBuilder.playbyplay_url(game_pk)
        return self._request(url)

    def get_person_stats(
        self,
        person_id: int,
        season: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Get person statistics.

        Args:
            person_id: Person ID
            season: Season year

        Returns:
            Person stats JSON
        """
        url = MLBEndpointBuilder.person_stats_url(person_id)
        params = MLBParamTransformer.person_params(
            person_id=person_id,
            season=season,
        )

        return self._request(url, params)