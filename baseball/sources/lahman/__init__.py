"""Lahman Baseball Database source.

Handles downloading and ingesting historical baseball data from
Sean Lahman's comprehensive baseball statistics database.
"""

from baseball.sources.lahman.downloader import LahmanDownloader

__all__ = ["LahmanDownloader"]
