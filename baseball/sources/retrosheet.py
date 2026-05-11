"""
================================================================================
Retrosheet Source Adapter
Name: retrosheet.py
Date: 2026-05-11
Script: retrosheet.py
Version: 1.0.0
Log Summary: Retrosheet client for historical play-by-play data
Description: Retrosheet event and roster file downloader and inventory
Change Summary: Initial implementation with file enumeration
Inputs: Season, file type (events, rosters, schedules)
Outputs: Raw Retrosheet files, parsed play-by-play data
================================================================================
"""

import os
from pathlib import Path
from typing import Dict, List, Optional

import httpx

from baseball.core.logging import get_logger

logger = get_logger(__name__)


class RetrosheetClient:
    """Client for Retrosheet historical baseball data."""

    BASE_URL = "https://www.retrosheet.org"

    FILE_TYPES = {
        "events": "game.log",
        "rosters": "roster",
        "schedules": "schedule",
    }

    def __init__(self, cache_dir: Optional[Path] = None, timeout: int = 30):
        """Initialize Retrosheet client.

        Args:
            cache_dir: Directory to cache downloads
            timeout: HTTP request timeout in seconds
        """
        self.cache_dir = cache_dir or Path("data/retrosheet")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)

    def get_available_seasons(self) -> List[int]:
        """Get list of available seasons.

        Returns:
            List of seasons with data
        """
        # Retrosheet has data from 1871-2024
        return list(range(1871, 2025))

    def download_events(
        self, season: int, force: bool = False
    ) -> Optional[str]:
        """Download event files for a season.

        Args:
            season: MLB season year
            force: Force redownload even if cached

        Returns:
            Path to downloaded file or None if failed
        """
        filename = f"{season}eve.zip"
        url = f"{self.BASE_URL}/retrosheet/events/{filename}"
        return self._download_file(url, filename, force=force)

    def download_rosters(
        self, season: int, force: bool = False
    ) -> Optional[str]:
        """Download roster files for a season.

        Args:
            season: MLB season year
            force: Force redownload even if cached

        Returns:
            Path to downloaded file or None if failed
        """
        filename = f"{season}ros.zip"
        url = f"{self.BASE_URL}/retrosheet/rosters/{filename}"
        return self._download_file(url, filename, force=force)

    def _download_file(
        self, url: str, filename: str, force: bool = False
    ) -> Optional[str]:
        """Download a file from Retrosheet.

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
