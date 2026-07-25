"""Lands Retrosheet's annual team rosters into raw.retrosheet_roster: one row
per player-team-season, 1871-2025 (retrosheet.org/rosters.zip). Each team's
season is its own headerless .ROS file inside the zip (player_id, last_name,
first_name, bats, throws, team_id, position); team and year aren't repeated
inside the file, so both are parsed from the filename ({team}{year}.ROS,
e.g. "WS11910.ROS" -> team "WS1", year "1910" — team codes can end in a
digit, so the split anchors on the fixed-length \\d{4} immediately before
".ROS" rather than a naive scan) and added as columns.

rosters.zip also bundles UMPIRES{year}.txt files (per-year umpire name
lists) — not loaded here, since biodata.zip's umpires0.csv (see
retrosheet_reference.py) already covers umpire identities with fuller
biographical fields. A genuinely separate connector if per-year umpire crew
assignments are ever needed, not silently folded into this one.

Whole-file download, full reload each run (small enough — a few MB
uncompressed) like the Chadwick register and Lahman.
"""

import re
import zipfile

import pandas as pd
import psycopg

from mlb_baseball import manifest
from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_last_run, check_table_has_rows
from mlb_baseball.ingest import track_run
from mlb_baseball.load import load_dataframe

SOURCE = "retrosheet_roster"
TABLE = "raw.retrosheet_roster"
ROSTER_FIELDS = ["player_id", "last_name", "first_name", "bats", "throws", "team_id", "position"]

_ROS_NAME_RE = re.compile(r"^([A-Z0-9]+)(\d{4})\.ROS$")


def _rosters() -> pd.DataFrame:
    path = manifest.download(SOURCE, "rosters.zip", "https://www.retrosheet.org/rosters.zip")
    frames = []
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            match = _ROS_NAME_RE.match(name)
            if not match:
                continue
            _, year = match.groups()
            with zf.open(name) as f:
                df = pd.read_csv(f, header=None, names=ROSTER_FIELDS)
            df["_season"] = year
            frames.append(df)
    manifest.mark_status(SOURCE, path.name, "loaded")
    return pd.concat(frames, ignore_index=True)


def _run(conn: psycopg.Connection) -> dict[str, int]:
    return {TABLE: load_dataframe(conn, TABLE, _rosters())}


def bootstrap() -> dict[str, int]:
    with get_connection() as conn, track_run(conn, SOURCE, "bootstrap") as result:
        counts = _run(conn)
        conn.commit()
        result["rows"] = sum(counts.values())
    return counts


def update() -> dict[str, int]:
    with get_connection() as conn, track_run(conn, SOURCE, "update") as result:
        counts = _run(conn)
        conn.commit()
        result["rows"] = sum(counts.values())
    return counts


def health_check() -> list[Check]:
    return [check_table_has_rows(TABLE), check_last_run(SOURCE)]
