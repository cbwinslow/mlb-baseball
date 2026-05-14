"""FanGraphs source.

Handles downloading player statistics and leaderboards from FanGraphs.
Uses URL-based CSV export (not an official API).
"""

from baseball.sources.fangraphs.downloader import FanGraphsDownloader

__all__ = ["FanGraphsDownloader"]
