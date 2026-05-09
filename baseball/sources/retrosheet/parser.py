
"""
================================================================================
Retrosheet Event File Parser
Date: 2026-05-09

Parse Retrosheet event files without external dependencies.
Can delegate to Chadwick tools if available.
================================================================================
"""

from datetime import date, datetime
from pathlib import Path
from typing import Iterator, Optional

from baseball.core.enums import ResultStatus, SourceType
from baseball.core.logging import get_logger
from baseball.core.results import ValidationResult
from baseball.sources.retrosheet.models import RetroEventLine, RetroGameEvent


logger = get_logger(__name__)


class RetroEventFileParser:
    """Parse Retrosheet event files."""

    def __init__(self):
        """Initialize parser."""
        pass

    def parse_file(
        self,
        path: Path,
    ) -> Iterator[RetroEventLine]:
        """Parse event file line by line.

        Args:
            path: Path to event file

        Yields:
            RetroEventLine objects
        """
        logger.info(f'Parsing {path}')

        game_id = None
        season = None

        with open(path) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    parts = line.split(',')
                    line_type = parts[0]

                    # Extract game ID and season
                    if line_type == 'id':
                        game_id = parts[1]
                        # Parse season from game ID (e.g., ATL20240101 → 2024)
                        season = int(game_id[3:7])

                    # Parse event line
                    if line_type == 'play':
                        event = self._parse_play_line(
                            parts,
                            game_id=game_id,
                            season=season,
                        )
                        if event:
                            yield event

                except Exception as e:
                    logger.warning(f'Error parsing line {line_num}: {e}')
                    continue

    def _parse_play_line(
        self,
        parts: list[str],
        game_id: Optional[str],
        season: Optional[int],
    ) -> Optional[RetroEventLine]:
        """Parse a play line.

        Format: play,inning,home-away,player_id,count,pitches,result,...

        Args:
            parts: Split line parts
            game_id: Game ID
            season: Season year

        Returns:
            RetroEventLine or None
        """
        if len(parts) < 7:
            return None

        return RetroEventLine(
            line_type='play',
            season=season or 0,
            game_id=game_id or '',
            inning=int(parts[1]),
            home_away=int(parts[2]),
            player_id=parts[3],
            metadata={
                'count': parts[4],
                'pitches': parts[5],
                'result': parts[6],
            },
        )

    def extract_games(
        self,
        path: Path,
    ) -> Iterator[dict]:
        """Extract game-level summaries from event file.

        Args:
            path: Path to event file

        Yields:
            Game summary dicts
        """
        game_id = None
        game_info = {}
        events = []

        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                parts = line.split(',')
                line_type = parts[0]

                if line_type == 'id':
                    # New game
                    if game_id and events:
                        yield {
                            'game_id': game_id,
                            'info': game_info,
                            'events': events,
                        }

                    game_id = parts[1]
                    game_info = {}
                    events = []

                elif line_type == 'info':
                    key = parts[1]
                    value = parts[2] if len(parts) > 2 else ''
                    game_info[key] = value

                elif line_type == 'play':
                    events.append(parts)

            # Yield last game
            if game_id and events:
                yield {
                    'game_id': game_id,
                    'info': game_info,
                    'events': events,
                }