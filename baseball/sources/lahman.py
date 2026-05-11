"""
================================================================================
Lahman Database Source Adapter
Name: lahman.py
Date: 2026-05-11
Script: lahman.py
Version: 1.0.0
Log Summary: Lahman historical baseball database source adapter
Description: Access to Lahman database for historical player and team stats
Change Summary: Initial implementation with file download support
Inputs: Season, player ID, team ID, data type
Outputs: Historical statistics, roster data
================================================================================
"""

from pathlib import Path
from typing import Dict, List, Optional

import httpx

from baseball.core.logging import get_logger

logger = get_logger(__name__)


class LahmanClient:
    """Client for Lahman historical baseball database."""

    BASE_URL = "https://www.seanlahman.com/files/database"

    # Available Lahman data files
    DATA_FILES = [
        "Batting.csv",
        "Pitching.csv",
        "Fielding.csv",
        "Master.csv",
        "Teams.csv",
        "Parks.csv",
    ]

    def __init__(self, cache_dir: Optional[Path] = None, timeout: int = 30):
        """Initialize Lahman client.

        Args:
            cache_dir: Directory to cache downloads
            timeout: HTTP request timeout in seconds
        """
        self.cache_dir = cache_dir or Path("data/lahman")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)

    def download_batting_data(self, force: bool = False) -> Optional[str]:
        """Download Lahman batting statistics.

        Args:
            force: Force redownload if cached

        Returns:
            Path to CSV file or None
        """
        filename = "Batting.csv"
        url = f"{self.BASE_URL}/Batting.csv"
        return self._download_file(url, filename, force=force)

    def download_pitching_data(self, force: bool = False) -> Optional[str]:
        """Download Lahman pitching statistics.

        Args:
            force: Force redownload if cached

        Returns:
            Path to CSV file or None
        """
        filename = "Pitching.csv"
        url = f"{self.BASE_URL}/Pitching.csv"
        return self._download_file(url, filename, force=force)

    def download_master_data(self, force: bool = False) -> Optional[str]:
        """Download Lahman master player file.

        Args:
            force: Force redownload if cached

        Returns:
            Path to CSV file or None
        """
        filename = "Master.csv"
        url = f"{self.BASE_URL}/Master.csv"
        return self._download_file(url, filename, force=force)

    def download_teams_data(self, force: bool = False) -> Optional[str]:
        """Download Lahman teams data.

        Args:
            force: Force redownload if cached

        Returns:
            Path to CSV file or None
        """
        filename = "Teams.csv"
        url = f"{self.BASE_URL}/Teams.csv"
        return self._download_file(url, filename, force=force)

    def _download_file(
        self, url: str, filename: str, force: bool = False
    ) -> Optional[str]:
        """Download a file from Lahman.

        Args:
            url: Full URL to download
            filename: Name to save as
            force: Force redownload

        Returns:
            Path to downloaded file or None
        """
        cache_path = self.cache_dir / filename

        if cache_path.exists() and not force:
            logger.info(f"Using cached file: {cache_path}")
            return str(cache_path)

        try:
            logger.info(f"Downloading: {url}")
            response = self.client.get(url)
            response.raise_for_status()

            with open(cache_path, "wb") as f:
                f.write(response.content)

            logger.info(f"Downloaded to: {cache_path}")
            return str(cache_path)
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            return None

    def close(self) -> None:
        """Close HTTP client."""
        self.client.close()
