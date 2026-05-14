"""FanGraphs source.

Handles downloading player statistics and leaderboards from FanGraphs.
Uses URL-based CSV export (not an official API).
"""

from baseball.sources.fangraphs.downloader import FanGraphsDownloader
from baseball.sources.fangraphs.ingestor import FanGraphsIngestor

__all__ = [
    "FanGraphsDownloader",
    "FangraphsIngestor",
]
