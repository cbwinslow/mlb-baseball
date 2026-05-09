"""
================================================================================
MLB Downloader
Date: 2026-05-09

High-level MLB data download orchestration.
================================================================================
"""

from datetime import datetime
from pathlib import Path

import pandas as pd

from baseball.core.enums import ResultStatus, SourceType
from baseball.core.logging import get_logger
from baseball.core.results import DownloadResult
from baseball.sources.common.files import save_csv, save_json
from baseball.sources.mlb.client import MLBClient

logger = get_logger(__name__)


class MLBDownloader:
    """Download MLB data from Stats API."""

    def __init__(
        self,
        output_dir: Path = Path("data/raw/mlb"),
        rate_limit: float = 0.5,
    ):
        """Initialize downloader.

        Args:
            output_dir: Output directory for raw files
            rate_limit: Rate limit for API requests
        """
        self.output_dir = Path(output_dir)
        self.client = MLBClient(rate_limit=rate_limit)

    def download_schedule(
        self,
        season: int | None = None,
        team_id: str | None = None,
    ) -> DownloadResult:
        """Download MLB schedule.

        Args:
            season: Season year
            team_id: Team ID (optional, filters to team)

        Returns:
            DownloadResult with download metadata
        """
        result = DownloadResult(
            source=SourceType.MLB,
            status=ResultStatus.FAILED,
        )
        result.start_time = datetime.now()

        try:
            logger.info(f"Downloading MLB schedule: season={season}, team={team_id}")

            # Fetch data
            data = self.client.get_schedule(season=season, team_id=team_id)

            # Parse into DataFrame
            games = []
            for date_block in data.get("dates", []):
                for game in date_block.get("games", []):
                    games.append(
                        {
                            "game_pk": game["gamePk"],
                            "game_date": game["gameDateTime"],
                            "season": game["season"],
                            "status": game["status"]["abstractGameCode"],
                            "home_team": game["teams"]["home"]["team"]["name"],
                            "away_team": game["teams"]["away"]["team"]["name"],
                        }
                    )

            df = pd.DataFrame(games)

            # Save to CSV
            filename = f"schedule_{season}_{team_id or 'all'}.csv"
            output_path = self.output_dir / filename
            save_csv(df, output_path)

            result.status = ResultStatus.SUCCESS
            result.rows_downloaded = len(df)
            result.files_downloaded = [output_path]
            result.bytes_downloaded = output_path.stat().st_size

            logger.info(f"Downloaded {len(df)} games to {output_path}")

        except Exception as e:
            result.error = str(e)
            result.error_code = "DOWNLOAD_ERROR"
            logger.exception(f"Download failed: {e}")

        finally:
            result.end_time = datetime.now()

        return result

    def download_game(
        self,
        game_pk: int,
        include_boxscore: bool = True,
        include_pbp: bool = True,
    ) -> DownloadResult:
        """Download individual game data.

        Args:
            game_pk: Game ID
            include_boxscore: Download boxscore
            include_pbp: Download play-by-play

        Returns:
            DownloadResult
        """
        result = DownloadResult(
            source=SourceType.MLB,
            status=ResultStatus.FAILED,
        )
        result.start_time = datetime.now()

        try:
            logger.info(f"Downloading game {game_pk}")

            # Fetch live feed
            feed_data = self.client.get_game_feed(game_pk)
            feed_path = self.output_dir / f"game_{game_pk}_feed.json"
            save_json(feed_data, feed_path)
            result.files_downloaded.append(feed_path)

            if include_boxscore:
                boxscore_data = self.client.get_boxscore(game_pk)
                boxscore_path = self.output_dir / f"game_{game_pk}_boxscore.json"
                save_json(boxscore_data, boxscore_path)
                result.files_downloaded.append(boxscore_path)

            if include_pbp:
                pbp_data = self.client.get_playbyplay(game_pk)
                pbp_path = self.output_dir / f"game_{game_pk}_pbp.json"
                save_json(pbp_data, pbp_path)
                result.files_downloaded.append(pbp_path)

            result.status = ResultStatus.SUCCESS
            result.rows_downloaded = 1  # One game

            logger.info(f"Downloaded game {game_pk}")

        except Exception as e:
            result.error = str(e)
            result.error_code = "DOWNLOAD_ERROR"
            logger.exception(f"Download failed: {e}")

        finally:
            result.end_time = datetime.now()

        return result
