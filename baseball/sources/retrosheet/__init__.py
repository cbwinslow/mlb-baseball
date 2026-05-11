"""Retrosheet event files source implementation.

Handles downloading, parsing, and ingesting Retrosheet historical baseball data
including event files, game logs, and other historical records.

Key features:
  - Event file downloads (`.EVA`, `.EVN` extensions)
  - Chadwick tool integration for standardization
  - Event parsing and normalization
  - Historical data validation
  - Play-by-play extraction
"""

from baseball.sources.retrosheet.downloader import RetroEventFileDownloader
from baseball.sources.retrosheet.ingestor import RetroEventFileIngestor
from baseball.sources.retrosheet.parser import RetroEventParser
from baseball.sources.retrosheet.validator import RetroDataValidator

__all__ = [
    "RetroEventFileDownloader",
    "RetroEventFileIngestor",
    "RetroEventParser",
    "RetroDataValidator",
]
