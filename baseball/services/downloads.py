"""
================================================================================
Download Services
Date: 2026-05-09

Orchestrate download workflows across all sources.
================================================================================
"""

from pathlib import Path

from baseball.core.logging import get_logger
from baseball.core.results import DownloadResult
from baseball.sources.espn.downloader import ESPNDownloader
from baseball.sources.fangraphs.downloader import FanGraphsDownloader
from baseball.sources.lahman.downloader import LahmanDownloader
from baseball.sources.mlb.downloader import MLBDownloader
from baseball.sources.retrosheet.downloader import RetroEventFileDownloader
from baseball.sources.statcast.downloader import StatcastDownloader
from baseball.sources.weather.downloader import WeatherDownloader

logger = get_logger(__name__)


# MLB Services
def download_mlb_season(
    season: int,
    team_id: str | None = None,
    output_dir: Path = Path("data/raw/mlb"),
) -> DownloadResult:
    """Download MLB season schedule."""
    logger.info(f"Download service: MLB season {season}, team={team_id}")
    downloader = MLBDownloader(output_dir=output_dir)
    return downloader.download_schedule(season=season, team_id=team_id)


def download_mlb_game(
    game_pk: int,
    output_dir: Path = Path("data/raw/mlb"),
) -> DownloadResult:
    """Download MLB game data."""
    logger.info(f"Download service: MLB game {game_pk}")
    downloader = MLBDownloader(output_dir=output_dir)
    return downloader.download_game(game_pk=game_pk)


# Retrosheet Services
def download_retrosheet_events(
    season: int,
    teams: list[str] | None = None,
    output_dir: Path = Path("data/raw/retrosheet"),
) -> DownloadResult:
    """Download Retrosheet event files."""
    logger.info(f"Download service: Retrosheet events {season}")
    downloader = RetroEventFileDownloader(output_dir=output_dir)
    return downloader.download_event_files(season=season, teams=teams)


def download_retrosheet_game_logs(
    season: int,
    league: str = "AL",
    output_dir: Path = Path("data/raw/retrosheet"),
) -> DownloadResult:
    """Download Retrosheet game logs."""
    logger.info(f"Download service: Retrosheet game logs {season} {league}")
    downloader = RetroEventFileDownloader(output_dir=output_dir)
    return downloader.download_game_logs(season=season, league=league)


# StatCast Services
def download_statcast_season(
    season: int,
    output_dir: Path = Path("data/raw/statcast"),
) -> DownloadResult:
    """Download StatCast data for season."""
    logger.info(f"Download service: StatCast season {season}")
    downloader = StatcastDownloader(output_dir=output_dir)
    return downloader.download_season(season=season)


def download_statcast_pitcher(
    pitcher_id: int,
    season: int | None = None,
    output_dir: Path = Path("data/raw/statcast"),
) -> DownloadResult:
    """Download StatCast data for pitcher."""
    logger.info(f"Download service: StatCast pitcher {pitcher_id}")
    downloader = StatcastDownloader(output_dir=output_dir)
    return downloader.download_pitcher(pitcher_id=pitcher_id, season=season)


def download_statcast_batter(
    batter_id: int,
    season: int | None = None,
    output_dir: Path = Path("data/raw/statcast"),
) -> DownloadResult:
    """Download StatCast data for batter."""
    logger.info(f"Download service: StatCast batter {batter_id}")
    downloader = StatcastDownloader(output_dir=output_dir)
    return downloader.download_batter(batter_id=batter_id, season=season)


# Lahman Services
def download_lahman(
    tables: list[str] | None = None,
    version: str = "latest",
    output_dir: Path = Path("data/raw/lahman"),
) -> DownloadResult:
    """Download Lahman database."""
    logger.info("Download service: Lahman database")
    downloader = LahmanDownloader(output_dir=output_dir)
    return downloader.download(tables=tables, version=version)


# FanGraphs Services
def download_fangraphs_batting(
    season: int,
    output_dir: Path = Path("data/raw/fangraphs"),
) -> DownloadResult:
    """Download FanGraphs batting stats."""
    logger.info(f"Download service: FanGraphs batting {season}")
    downloader = FanGraphsDownloader(output_dir=output_dir)
    return downloader.download_batting_stats(season=season)


def download_fangraphs_pitching(
    season: int,
    output_dir: Path = Path("data/raw/fangraphs"),
) -> DownloadResult:
    """Download FanGraphs pitching stats."""
    logger.info(f"Download service: FanGraphs pitching {season}")
    downloader = FanGraphsDownloader(output_dir=output_dir)
    return downloader.download_pitching_stats(season=season)


# ESPN Services
def download_espn_scoreboard(
    date_str: str | None = None,
    output_dir: Path = Path("data/raw/espn"),
) -> DownloadResult:
    """Download ESPN scoreboard."""
    logger.info("Download service: ESPN scoreboard")
    downloader = ESPNDownloader(output_dir=output_dir)
    return downloader.download_scoreboard(date_str=date_str)


# Weather Services
def download_weather_forecast(
    latitude: float,
    longitude: float,
    venue_name: str,
    output_dir: Path = Path("data/raw/weather"),
) -> DownloadResult:
    """Download weather forecast."""
    logger.info(f"Download service: Weather {venue_name}")
    downloader = WeatherDownloader(output_dir=output_dir)
    return downloader.download_forecast(
        latitude=latitude,
        longitude=longitude,
        venue_name=venue_name,
    )
