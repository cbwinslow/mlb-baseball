"""Lands the Lahman Baseball Database into raw.lahman_*.

SABR's current release (https://sabr.org/lahman-database/) is distributed only
via a Box.com folder with no stable, scriptable direct-download URL — confirmed
by testing (Box's API requires an app-registered OAuth token; anonymous folder
downloads only work through the interactive web UI). That makes it a manual
download: see docs/DATA_SOURCES.md for the exact steps. This connector prefers
a local copy over `downloads/`, and only falls back to a network fetch (pinned
to a preserved fork, frozen at the 2021 season — see docs/DECISIONS.md) if no
local copy is present, printing a clear warning when it does.

Table names and CSV filenames below match Lahman's own naming (snake_cased,
not abbreviated) rather than our usual "one or two words" convention — see the
naming-convention exemption for established source vocabularies in CLAUDE.md.

Like the register, this is a frozen/point-in-time source as far as we're
concerned, so bootstrap() and update() are the same full reload.
"""

import zipfile
from pathlib import Path

import pandas as pd
import pybaseball.lahman as network_lahman

from mlb_baseball.db import get_connection
from mlb_baseball.health import (
    DAILY_FRESHNESS_THRESHOLD_MINUTES,
    Check,
    check_last_run,
    check_recent_run,
    check_table_has_rows,
)
from mlb_baseball.ingest import track_run
from mlb_baseball.load import load_dataframe

# Fallback only — see module docstring. base_string ("baseballdatabank-master")
# already matches our fork's default branch, so only the zip URL needs to change.
network_lahman.url = "https://github.com/cbwinslow/baseballdatabank/archive/refs/heads/master.zip"

SOURCE = "lahman"
FRESHNESS_THRESHOLD_MINUTES = DAILY_FRESHNESS_THRESHOLD_MINUTES
DOWNLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "downloads"

# (raw table name, Lahman's own CSV filename, network fallback function)
TABLES = [
    ("raw.lahman_people", "People.csv", network_lahman.people),
    ("raw.lahman_batting", "Batting.csv", network_lahman.batting),
    ("raw.lahman_batting_post", "BattingPost.csv", network_lahman.batting_post),
    ("raw.lahman_pitching", "Pitching.csv", network_lahman.pitching),
    ("raw.lahman_pitching_post", "PitchingPost.csv", network_lahman.pitching_post),
    ("raw.lahman_fielding", "Fielding.csv", network_lahman.fielding),
    ("raw.lahman_fielding_of", "FieldingOF.csv", network_lahman.fielding_of),
    ("raw.lahman_fielding_of_split", "FieldingOFsplit.csv", network_lahman.fielding_of_split),
    ("raw.lahman_fielding_post", "FieldingPost.csv", network_lahman.fielding_post),
    ("raw.lahman_appearances", "Appearances.csv", network_lahman.appearances),
    ("raw.lahman_allstar_full", "AllstarFull.csv", network_lahman.all_star_full),
    ("raw.lahman_awards_managers", "AwardsManagers.csv", network_lahman.awards_managers),
    ("raw.lahman_awards_players", "AwardsPlayers.csv", network_lahman.awards_players),
    (
        "raw.lahman_awards_share_managers",
        "AwardsShareManagers.csv",
        network_lahman.awards_share_managers,
    ),
    (
        "raw.lahman_awards_share_players",
        "AwardsSharePlayers.csv",
        network_lahman.awards_share_players,
    ),
    ("raw.lahman_college_playing", "CollegePlaying.csv", network_lahman.college_playing),
    ("raw.lahman_hall_of_fame", "HallOfFame.csv", network_lahman.hall_of_fame),
    ("raw.lahman_home_games", "HomeGames.csv", network_lahman.home_games),
    ("raw.lahman_managers", "Managers.csv", network_lahman.managers),
    ("raw.lahman_managers_half", "ManagersHalf.csv", network_lahman.managers_half),
    ("raw.lahman_parks", "Parks.csv", network_lahman.parks),
    ("raw.lahman_salaries", "Salaries.csv", network_lahman.salaries),
    ("raw.lahman_schools", "Schools.csv", network_lahman.schools),
    ("raw.lahman_series_post", "SeriesPost.csv", network_lahman.series_post),
    ("raw.lahman_teams", "Teams.csv", network_lahman.teams_core),
    ("raw.lahman_teams_franchises", "TeamsFranchises.csv", network_lahman.teams_franchises),
    ("raw.lahman_teams_half", "TeamsHalf.csv", network_lahman.teams_half),
]


def find_local_zip() -> Path | None:
    matches = sorted(DOWNLOADS_DIR.glob("lahman*.zip"), key=lambda p: p.stat().st_mtime)
    return matches[-1] if matches else None


def _read_from_zip(zf: zipfile.ZipFile, filename: str) -> pd.DataFrame:
    (member,) = (n for n in zf.namelist() if n.endswith(f"/{filename}") or n == filename)
    with zf.open(member) as f:
        return pd.read_csv(f)


def _run(mode: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    zip_path = find_local_zip()
    with get_connection() as conn, track_run(conn, SOURCE, mode) as result:
        if zip_path:
            print(f"lahman: loading current data from local {zip_path}")
            with zipfile.ZipFile(zip_path) as zf:
                for table, filename, _fetch in TABLES:
                    df = _read_from_zip(zf, filename)
                    counts[table] = load_dataframe(conn, table, df)
        else:
            print(
                "lahman: WARNING — no local zip found in downloads/, falling back to a "
                "network source frozen at the 2021 season. For current data, see the "
                "manual download steps in docs/DATA_SOURCES.md."
            )
            for table, _filename, fetch in TABLES:
                df = fetch()
                counts[table] = load_dataframe(conn, table, df)
        conn.commit()
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
                False,
                "no local zip in downloads/ — data may be frozen at the 2021 network fallback",
            )
        )
    return checks
