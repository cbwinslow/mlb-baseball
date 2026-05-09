"""
================================================================================
MLB Live Game Polling
Date: 2026-05-09

Real-time game polling with change detection and deduplication.
================================================================================
"""

import hashlib
import json
import time
from collections.abc import AsyncIterator
from datetime import datetime

from baseball.core.enums import SourceType
from baseball.core.logging import get_logger
from baseball.core.results import LiveUpdate
from baseball.sources.mlb.client import MLBClient
from baseball.sources.mlb.models import MLBGameState

logger = get_logger(__name__)


class MLBLivePoller:
    """Poll MLB live game feeds with change detection."""

    def __init__(self, rate_limit: float = 0.5):
        """Initialize live poller.

        Args:
            rate_limit: Rate limit for API requests
        """
        self.client = MLBClient(rate_limit=rate_limit)
        self._state_cache: dict = {}
        self._play_hashes: set = set()

    def _compute_hash(self, obj: dict) -> str:
        """Compute hash of object for deduplication.

        Args:
            obj: Object to hash

        Returns:
            Hex-encoded SHA256 hash
        """
        json_str = json.dumps(obj, sort_keys=True, default=str)
        return hashlib.sha256(json_str.encode()).hexdigest()

    def _extract_game_state(self, feed: dict) -> MLBGameState:
        """Extract game state from live feed.

        Args:
            feed: Live feed JSON

        Returns:
            Parsed game state
        """
        game_data = feed.get("gameData", {})
        live_data = feed.get("liveData", {})

        return MLBGameState(
            game_pk=feed["gamePk"],
            game_date=datetime.fromisoformat(
                game_data.get("datetime", {}).get("dateTime", "").replace("Z", "+00:00")
            ),
            status=live_data.get("gameState", ""),
            inning=live_data.get("linescore", {}).get("currentInning"),
            inning_state=live_data.get("linescore", {}).get("inningState"),
            home_team=game_data.get("teams", {}).get("home", {}).get("teamName", ""),
            away_team=game_data.get("teams", {}).get("away", {}).get("teamName", ""),
            home_score=live_data.get("linescore", {})
            .get("teams", {})
            .get("home", {})
            .get("runs", 0),
            away_score=live_data.get("linescore", {})
            .get("teams", {})
            .get("away", {})
            .get("runs", 0),
        )

    async def poll(
        self,
        game_pk: int,
        poll_interval: int = 10,
        max_polls: int | None = None,
        timeout_seconds: int | None = None,
    ) -> AsyncIterator[LiveUpdate]:
        """Poll live game feed.

        Args:
            game_pk: Game ID
            poll_interval: Seconds between polls
            max_polls: Maximum number of polls
            timeout_seconds: Total polling timeout

        Yields:
            LiveUpdate objects with changes
        """
        start_time = time.time()
        poll_count = 0

        try:
            while True:
                # Check timeout
                if timeout_seconds and (time.time() - start_time) > timeout_seconds:
                    logger.info(f"Polling timeout reached for game {game_pk}")
                    break

                # Check poll limit
                if max_polls and poll_count >= max_polls:
                    logger.info(f"Max polls reached for game {game_pk}")
                    break

                poll_count += 1

                try:
                    # Fetch current game state
                    feed = self.client.get_game_feed(game_pk)

                    # Extract game state
                    game_state = self._extract_game_state(feed)

                    # Detect changes
                    new_plays = []
                    plays = feed.get("liveData", {}).get("plays", [])

                    for play in plays:
                        play_hash = self._compute_hash(play)
                        if play_hash not in self._play_hashes:
                            self._play_hashes.add(play_hash)
                            new_plays.append(play)

                    # Create update
                    update = LiveUpdate(
                        source=SourceType.MLB,
                        game_pk=game_pk,
                        timestamp=datetime.now(),
                        new_records=new_plays,
                        game_state=game_state.model_dump(),
                    )

                    yield update

                    # Check if game is finished
                    if game_state.status in ("F", "O", "GF"):
                        logger.info(f"Game {game_pk} finished")
                        break

                except Exception as e:
                    logger.warning(f"Poll error for game {game_pk}: {e}")
                    # Continue polling on errors

                # Wait before next poll
                time.sleep(poll_interval)

        except KeyboardInterrupt:
            logger.info(f"Polling interrupted for game {game_pk}")
