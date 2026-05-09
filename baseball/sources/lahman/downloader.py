
"""
================================================================================
Lahman Database Downloader
Date: 2026-05-09

Download Lahman Baseball Database CSV files.
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


logger = get_logger(__name__)


class LahmanDownloader:
    """Download Lahman Baseball Database."""

    BASE_URL = 'http://seanlahman.com/files/database/'
    DEFAULT_VERSION = '2024.1'

    # Common tables
    COMMON_TABLES = [
        'people', 'batting', 'pitching', 'fielding',
        'teams', 'appearances', 'managers', 'salaries',
    ]

    def __init__(self, output_dir: Path = Path('data/raw/lahman')):
        """Initialize downloader.

        Args:
            output_dir: Output directory
        """
        self.output_dir = Path(output_dir)
        self.client = httpx.Client(timeout=120.0)

    def download(
        self,
        tables: Optional[list[str]] = None,
        version: str = DEFAULT_VERSION,
    ) -> DownloadResult:
        """Download Lahman database ZIP.

        Args:
            tables: Optional list of tables to extract (all if None)
            version: Database version

        Returns:
            DownloadResult
        """
        result = DownloadResult(
            source=SourceType.LAHMAN,
            status=ResultStatus.FAILED,
        )
        result.start_time = datetime.now()

        try:
            # Build URL
            filename = f'baseballdatabank-{version}.zip'
            url = f'{self.BASE_URL}{filename}'

            logger.info(f'Downloading Lahman {version} from {url}')

            response = self.client.get(url)
            response.raise_for_status()

            result.bytes_downloaded = len(response.content)

            # Extract ZIP
            tables_to_extract = tables or self.COMMON_TABLES
            self.output_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
                # Find CSV directory in ZIP
                csv_prefix = None
                for name in zf.namelist():
                    if name.endswith('.csv'):
                        parts = name.split('/')
                        if len(parts) >= 2:
                            csv_prefix = '/'.join(parts[:-1])
                            break

                if not csv_prefix:
                    result.error = 'Could not find CSV files in ZIP'
                    return result

                # Extract specified tables
                for table in tables_to_extract:
                    csv_path = f'{csv_prefix}/{table}.csv'

                    try:
                        with zf.open(csv_path) as f:
                            content = f.read()
                            output_file = self.output_dir / f'{table}.csv'
                            output_file.write_bytes(content)
                            result.files_downloaded.append(output_file)
                            result.rows_downloaded += 1

                            logger.info(f'Extracted {table}.csv')

                    except KeyError:
                        logger.warning(f'{table}.csv not found in ZIP')

            result.status = ResultStatus.SUCCESS
            logger.info(f'Downloaded {len(result.files_downloaded)} tables')

        except Exception as e:
            result.error = str(e)
            result.error_code = 'DOWNLOAD_ERROR'
            logger.exception(f'Download failed: {e}')

        finally:
            result.end_time = datetime.now()

        return result