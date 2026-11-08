"""Lands the Lahman Baseball Database into raw.lahman_*, typed (ADR-304).

SABR publishes the current release only through a Box.com folder with no scriptable URL, so
this connector prefers a local copy in ``downloads/`` (drop SABR's zip there) and otherwise
downloads the owner's unedited mirror of the same release,
https://github.com/cbwinslow/lahman-database-csv (main branch). Loading goes through the staged
ingestion layer (``ingest_layer/sources/lahman.py``): every table has a declared schema, values
are the source text cast to those types (``NA`` stays ``NA``), one ledger item per table.

Table names and CSV filenames match Lahman's own naming (snake_cased, not abbreviated) rather
than our usual "one or two words" convention (the established-source-vocabulary exemption).
A frozen source: bootstrap() and update() are the same full reload.
"""

import zipfile
from pathlib import Path

import pandas as pd
import requests

from mlb_baseball.db import get_connection
from mlb_baseball.health import (
    DAILY_FRESHNESS_THRESHOLD_MINUTES,
    Check,
    check_last_run,
    check_recent_run,
    check_table_has_rows,
)
from mlb_baseball.ingest import track_run

SOURCE = "lahman"
FRESHNESS_THRESHOLD_MINUTES = DAILY_FRESHNESS_THRESHOLD_MINUTES
DOWNLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "downloads"
RELEASE_URL = "https://github.com/cbwinslow/lahman-database-csv/archive/refs/heads/main.zip"

# (raw table name, Lahman's own CSV filename)
TABLES = [
    ("raw.lahman_people", "People.csv"),
    ("raw.lahman_batting", "Batting.csv"),
    ("raw.lahman_batting_post", "BattingPost.csv"),
    ("raw.lahman_pitching", "Pitching.csv"),
    ("raw.lahman_pitching_post", "PitchingPost.csv"),
    ("raw.lahman_fielding", "Fielding.csv"),
    ("raw.lahman_fielding_of", "FieldingOF.csv"),
    ("raw.lahman_fielding_of_split", "FieldingOFsplit.csv"),
    ("raw.lahman_fielding_post", "FieldingPost.csv"),
    ("raw.lahman_appearances", "Appearances.csv"),
    ("raw.lahman_allstar_full", "AllstarFull.csv"),
    ("raw.lahman_awards_managers", "AwardsManagers.csv"),
    ("raw.lahman_awards_players", "AwardsPlayers.csv"),
    ("raw.lahman_awards_share_managers", "AwardsShareManagers.csv"),
    ("raw.lahman_awards_share_players", "AwardsSharePlayers.csv"),
    ("raw.lahman_college_playing", "CollegePlaying.csv"),
    ("raw.lahman_hall_of_fame", "HallOfFame.csv"),
    ("raw.lahman_home_games", "HomeGames.csv"),
    ("raw.lahman_managers", "Managers.csv"),
    ("raw.lahman_managers_half", "ManagersHalf.csv"),
    ("raw.lahman_parks", "Parks.csv"),
    ("raw.lahman_salaries", "Salaries.csv"),
    ("raw.lahman_schools", "Schools.csv"),
    ("raw.lahman_series_post", "SeriesPost.csv"),
    ("raw.lahman_teams", "Teams.csv"),
    ("raw.lahman_teams_franchises", "TeamsFranchises.csv"),
    ("raw.lahman_teams_half", "TeamsHalf.csv"),
]


def find_local_zip() -> Path | None:
    matches = sorted(DOWNLOADS_DIR.glob("lahman*.zip"), key=lambda p: p.stat().st_mtime)
    return matches[-1] if matches else None


def _read_from_zip(zf: zipfile.ZipFile, filename: str) -> pd.DataFrame:
    """The legacy pandas read. Kept only so tests can show what it corrupted (``NA`` -> NULL,
    ``4`` -> ``4.0``); loading uses ``ingest_layer`` and never this."""
    (member,) = (n for n in zf.namelist() if n.endswith(f"/{filename}") or n == filename)
    with zf.open(member) as f:
        return pd.read_csv(f)


def download_release() -> Path:
    """Fetch the mirror's main branch into ``downloads/`` (name carries the content hash, so
    an unchanged release is the same file) and return its path."""
    import hashlib

    response = requests.get(RELEASE_URL, timeout=120)
    response.raise_for_status()
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    path = DOWNLOADS_DIR / f"lahman_mirror_{hashlib.sha256(response.content).hexdigest()[:12]}.zip"
    if not path.exists():
        path.write_bytes(response.content)
    return path


def _run(mode: str) -> dict[str, int]:
    from mlb_baseball.ingest_layer.sources.lahman import land_zip

    zip_path = find_local_zip()
    if zip_path:
        print(f"lahman: loading from local {zip_path}")
    else:
        print(f"lahman: no local zip in downloads/, downloading {RELEASE_URL}")
        zip_path = download_release()
    with get_connection() as conn, track_run(conn, SOURCE, mode) as result:
        counts = land_zip(get_connection, zip_path)
        result["rows"] = sum(counts.values())
    return counts


def bootstrap() -> dict[str, int]:
    return _run("bootstrap")


def update() -> dict[str, int]:
    return _run("update")


def health_check() -> list[Check]:
    checks = [
        check_table_has_rows("raw.lahman_batting"),
        check_last_run(SOURCE),
        check_recent_run(SOURCE, FRESHNESS_THRESHOLD_MINUTES),
    ]
    zip_path = find_local_zip()
    if zip_path:
        checks.append(Check("lahman data currency", True, f"local zip present: {zip_path.name}"))
    else:
        checks.append(
            Check(
                "lahman data currency",
                True,
                "no local zip in downloads/: the next run downloads the owner's mirror "
                "(github.com/cbwinslow/lahman-database-csv)",
            )
        )
    return checks
