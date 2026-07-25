"""Lands Retrosheet play-by-play into raw.retrosheet_event, one row per event.

Source is a git repo (chadwickbureau/retrosheet), one directory per season
(1871-present) containing per-team event files plus the TEAM{year} and *.ROS
files cwevent needs to resolve players. Fully scriptable — unlike Lahman, no
manual download step. Parsing goes through the cwevent CLI tool (see
docs/TOOLS.md for why: pychadwick's Python binding doesn't build), not a
custom parser.

Unlike the register/Lahman (small enough to fully reload every run), history
here is ~155 seasons — reprocessing all of it on every call would be wasteful
and slow. Each season is loaded independently via load_dataframe's
scope_column, replacing only that season's rows. bootstrap() processes every
season and commits after each one (not one giant transaction) so a failure
partway through a multi-hour first run doesn't lose already-loaded seasons —
re-running is safe either way since each season's load is independently
idempotent. update() only reprocesses the current season, the only one that
still changes.

Column names are cwevent's own (lowercased) — Retrosheet's established
vocabulary, same naming exemption as Lahman (see CLAUDE.md).
"""

import io
import subprocess
from datetime import date
from pathlib import Path

import pandas as pd
import psycopg

from mlb_baseball.db import get_connection
from mlb_baseball.ingest import track_run
from mlb_baseball.load import load_dataframe

SOURCE = "retrosheet"
TABLE = "raw.retrosheet_event"
REPO_URL = "https://github.com/chadwickbureau/retrosheet.git"
REPO_DIR = Path(__file__).resolve().parent.parent.parent / "downloads" / "retrosheet"
FIELDS = "0-66"  # every standard cwevent field — see `cwevent -d`


def sync_repo() -> None:
    if REPO_DIR.exists():
        subprocess.run(["git", "-C", str(REPO_DIR), "pull", "--ff-only"], check=True)
    else:
        REPO_DIR.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", REPO_URL, str(REPO_DIR)], check=True)


def season_years() -> list[int]:
    seasons_dir = REPO_DIR / "seasons"
    return sorted(int(p.name) for p in seasons_dir.iterdir() if p.is_dir() and p.name.isdigit())


def _event_files(year: int) -> list[Path]:
    season_dir = REPO_DIR / "seasons" / str(year)
    return sorted(season_dir.glob(f"{year}*.EV?"))


def _run_cwevent(year: int) -> pd.DataFrame:
    season_dir = REPO_DIR / "seasons" / str(year)
    files = _event_files(year)
    result = subprocess.run(
        ["cwevent", "-q", "-y", str(year), "-f", FIELDS, "-n", *(f.name for f in files)],
        cwd=season_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    df = pd.read_csv(io.StringIO(result.stdout))
    df["_season"] = str(year)
    return df


def _load_season(conn: psycopg.Connection, year: int) -> int:
    df = _run_cwevent(year)
    return load_dataframe(conn, TABLE, df, scope_column="_season", scope_value=str(year))


def bootstrap() -> dict[str, int]:
    sync_repo()
    counts: dict[str, int] = {}
    with get_connection() as conn, track_run(conn, SOURCE, "bootstrap") as result:
        for year in season_years():
            counts[f"{TABLE} ({year})"] = _load_season(conn, year)
            conn.commit()
        result["rows"] = sum(counts.values())
    return {TABLE: sum(counts.values())}


def update() -> dict[str, int]:
    sync_repo()
    year = date.today().year
    with get_connection() as conn, track_run(conn, SOURCE, "update") as result:
        rows = _load_season(conn, year)
        conn.commit()
        result["rows"] = rows
    return {TABLE: rows}
