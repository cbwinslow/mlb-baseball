"""
================================================================================
Sources Package
Name: __init__.py
Date: 2026-05-11
Version: 1.0.0
Description: Data source adapters and downloaders
================================================================================
"""

from baseball.sources.mlbstatsapi import MLBStatsAPIClient
from baseball.sources.retrosheet import RetrosheetClient
from baseball.sources.statcast import StatcastClient

__all__ = [
    "MLBStatsAPIClient",
    "RetrosheetClient",
    "StatcastClient",
]
