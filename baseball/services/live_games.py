
"""
================================================================================
Live Game Services
Date: 2026-05-09

Orchestrate live game polling workflows.
================================================================================
"""

from typing import AsyncIterator, Optional

from baseball.core.logging import get_logger
from baseball.core.results import LiveUpdate
from baseball.sources.mlb.live import MLBLivePoller


logger = get_logger(__name__)


async def poll_live_mlb_game(
    game_pk: int,
    poll_interval: int = 10,
    max_polls: Optional[int] = None,
    timeout_seconds: Optional[int] = None,
) -> AsyncIterator[LiveUpdate]:
    """Poll a live MLB game.

    Args:
        game_pk: Game ID
        poll_interval: Seconds between polls
        max_polls: Maximum number of polls
        timeout_seconds: Total polling timeout

    Yields:
        LiveUpdate objects
    """
    logger.info(f'Live service: polling game {game_pk}')

    poller = MLBLivePoller()
    async for update in poller.poll(
        game_pk=game_pk,
        poll_interval=poll_interval,
        max_polls=max_polls,
        timeout_seconds=timeout_seconds,
    ):
        yield update