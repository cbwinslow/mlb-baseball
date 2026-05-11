"""StatCast pitch-level data source.

Handles downloading and ingesting StatCast data from Baseball Savant.
Uses pybaseball as internal implementation but provides baseball namespace API.
"""

from baseball.sources.statcast.downloader import StatcastDownloader
from baseball.sources.statcast.ingestor import StatcastIngestor

__all__ = [
    "StatcastDownloader",
    "StatcastIngestor",
]
