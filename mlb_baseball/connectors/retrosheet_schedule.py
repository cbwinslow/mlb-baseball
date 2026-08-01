"""Lands Retrosheet's planned schedules (retrosheet.org/schedule/schedule.zip)
into raw.retrosheet_schedule: one row per scheduled game, 1877-2026, including
postponement reason and makeup date where applicable. The zip already
contains one headered CSV per year ({year}schedule.csv) — no manual field
list needed, unlike the gamelog/event-file products.

The source header repeats "League"/"Game" for both the visiting and home
team (Date,Num,Day,Visitor,League,Game,Home,League,Game,Day/Night,
Postponed,Makeup); pandas would otherwise land them as indistinguishable
league_1/game_1 columns, so they're explicitly renamed to visitor_league/
visitor_game/home_league/home_game — a clarity fix, not a data change.

Whole-file download, full reload each run (small — a few MB total).
"""

import zipfile

import pandas as pd
import psycopg

from mlb_baseball import manifest
from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_last_run, check_table_has_rows
from mlb_baseball.ingest import track_run
from mlb_baseball.load import load_dataframe

SOURCE = "retrosheet_schedule"
TABLE = "raw.retrosheet_schedule"
COLUMN_RENAMES = {
    "League": "visitor_league",
    "Game": "visitor_game",
    "League.1": "home_league",
    "Game.1": "home_game",
}


def _schedules() -> pd.DataFrame:
    path = manifest.download_required(
        SOURCE, "schedule.zip", "https://www.retrosheet.org/schedule/schedule.zip"
    )
    frames = []
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.endswith("schedule.csv"):
                continue
            year = name[:4]
            with zf.open(name) as f:
                df = pd.read_csv(f).rename(columns=COLUMN_RENAMES)
            df["_season"] = year
            frames.append(df)
    manifest.mark_status(SOURCE, path.name, "loaded")
    return pd.concat(frames, ignore_index=True)


def _run(conn: psycopg.Connection) -> dict[str, int]:
    return {TABLE: load_dataframe(conn, TABLE, _schedules())}


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
