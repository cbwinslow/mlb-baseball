
"""
================================================================================
Retrosheet Downloader
Date: 2026-05-09

Download Retrosheet historical data files.
================================================================================
"""

import io
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from baseball.core.enums import ResultStatus, SourceType
from baseball.core.logging import get_logger
from baseball.core.results import DownloadResult
from baseball.sources.common.files import save_json


logger = get_logger(__name__)


class RetroEventFileDownloader:
    """Download Retrosheet event files."""

    BASE_URL = 'https://www.retrosheet.org/events/'
    
    # Mapping of team ID to Retrosheet abbreviation
    TEAM_CODES = {
        'NYY': 'NYA', 'BOS': 'BOS', 'BAL': 'BAL', 'TB': 'TBA',
        'TOR': 'TOR', 'DET': 'DET', 'KC': 'KCA', 'MIN': 'MIN',
        'CWS': 'CHA', 'CLE': 'CLE', 'OAK': 'OAK', 'LAA': 'ANA',
        'SEA': 'SEA', 'TEX': 'TEX', 'PHI': 'PHI', 'ATL': 'ATL',
        'NYM': 'NYN', 'WSH': 'WAS', 'MIA': 'MIA', 'STL': 'STL',
        'PIT': 'PIT', 'CHC': 'CHN', 'MIL': 'MIL', 'SD': 'SDN',
        'SF': 'SFN', 'LAD': 'LAN', 'ARI': 'ARI', 'COL': 'COL',
        'HOU': 'HOU',
    }

    def __init__(self, output_dir: Path = Path('data/raw/retrosheet')):
        """Initialize downloader.

        Args:
            output_dir: Output directory for files
        """
        self.output_dir = Path(output_dir)
        self.client = httpx.Client(timeout=60.0)

    def download_event_files(
        self,
        season: int,
        teams: Optional[list[str]] = None,
    ) -> DownloadResult:
        """Download Retrosheet event files for season.

        Args:
            season: Season year
            teams: Optional list of teams (e.g., ['NYY', 'BOS'])

        Returns:
            DownloadResult
        """
        result = DownloadResult(
            source=SourceType.RETROSHEET,
            status=ResultStatus.FAILED,
        )
        result.start_time = datetime.now()

        try:
            logger.info(f'Downloading Retrosheet event files for {season}')

            # Build download URL for season
            # Format: https://www.retrosheet.org/events/YYYY.zip
            url = f'{self.BASE_URL}{season}.zip'

            logger.debug(f'Downloading from {url}')

            response = self.client.get(url)
            response.raise_for_status()

            # Extract ZIP file
            season_dir = self.output_dir / str(season)
            season_dir.mkdir(parents=True, exist_ok=True)

            files_extracted = 0
            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                for file_info in zf.filelist:
                    filename = file_info.filename

                    # Filter by teams if specified
                    if teams:
                        team_codes = [self.TEAM_CODES.get(t, t) for t in teams]
                        if not any(code in filename.upper() for code in team_codes):
                            continue

                    # Extract event files (.EVx)
                    if filename.upper().endswith(('.EVA', '.EVN')):
                        content = zf.read(filename)
                        output_file = season_dir / filename
                        output_file.write_bytes(content)
                        result.files_downloaded.append(output_file)
                        files_extracted += 1
                        result.bytes_downloaded += len(content)

            result.status = ResultStatus.SUCCESS
            result.rows_downloaded = files_extracted
            logger.info(f'Extracted {files_extracted} event files for {season}')

        except Exception as e:
            result.error = str(e)
            result.error_code = 'DOWNLOAD_ERROR'
            logger.exception(f'Download failed: {e}')

        finally:
            result.end_time = datetime.now()

        return result

    def download_game_logs(
        self,
        season: int,
        league: str = 'AL',
    ) -> DownloadResult:
        """Download Retrosheet game logs for season.

        Args:
            season: Season year
            league: League (AL or NL)

        Returns:
            DownloadResult
        """
        result = DownloadResult(
            source=SourceType.RETROSHEET,
            status=ResultStatus.FAILED,
        )
        result.start_time = datetime.now()

        try:
            logger.info(f'Downloading {league} game logs for {season}')

            # Game logs: GL{year}{league}.TXT
            filename = f'GL{season}{league}.TXT'
            url = f'{self.BASE_URL}{filename}'

            response = self.client.get(url)
            response.raise_for_status()

            output_dir = self.output_dir / str(season)
            output_dir.mkdir(parents=True, exist_ok=True)
            output_file = output_dir / filename

            output_file.write_text(response.text)
            result.files_downloaded.append(output_file)
            result.bytes_downloaded = len(response.content)
            result.rows_downloaded = len(response.text.split('\n'))

            result.status = ResultStatus.SUCCESS
            logger.info(f'Downloaded {league} game logs for {season}')

        except Exception as e:
            result.error = str(e)
            result.error_code = 'DOWNLOAD_ERROR'
            logger.exception(f'Download failed: {e}')

        finally:
            result.end_time = datetime.now()

        return result