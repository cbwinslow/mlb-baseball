"""Lands Retrosheet's reference/dimension files into raw.retrosheet_*: ballpark
codes, team ID history, and biographical/coaching/relatives data. All are
static whole-file downloads (not per-year), so bootstrap() and update() are
the same full-reload operation — like the Chadwick register and Lahman.

- Park codes: retrosheet.org/parkcode.txt — already headered CSV.
- Team ID history: retrosheet.org/TEAMABR.TXT — headerless; layout (6 fields:
  team ID, league, city, nickname, first year, last year) confirmed against
  TeamIDs.htm and verified against the real downloaded file before hardcoding.
  Retrosheet's official published file is dated 2020 and has 2021 as the
  shared latest season for current franchises. Raw preserves that source fact;
  core deliberately interprets the shared maximum as open-ended.
- Biographical data: retrosheet.org/biofile.zip, containing four already-
  headered CSVs (biofile.csv, biofile0.csv — two different schemas Retrosheet
  distributes side by side, both landed as-is since raw stays source-faithful;
  coaches.csv; relatives.csv).
- retrosheet.org/downloads/biodata.zip — a newer reference bundle Retrosheet
  also distributes. Compared byte-for-byte against biofile.zip: biofile0.csv
  and relatives.csv are identical in both (fetched once, from biofile.zip,
  not duplicated), but biodata.zip additionally has managers0.csv and
  umpires0.csv (nothing comparable in biofile.zip — genuinely new tables),
  plus teams0.csv and coaches0.csv, which use different column layouts than
  the existing team/coach tables (start/end vs first_g/last_g) rather than
  being strictly richer — landed as their own tables (suffix "0", mirroring
  Retrosheet's own biofile/biofile0 naming) rather than silently merged.

Downloads land on disk first (downloads/retrosheet_reference/, tracked in a
JSON manifest — see mlb_baseball/manifest.py) before parsing.
"""

import zipfile

import pandas as pd
import psycopg

from mlb_baseball import manifest
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

SOURCE = "retrosheet_reference"
FRESHNESS_THRESHOLD_MINUTES = DAILY_FRESHNESS_THRESHOLD_MINUTES
TEAM_FIELDS = ["team_id", "league", "city", "nickname", "first_year", "last_year"]

BIOFILE_MEMBERS = {
    "biofile.csv": "raw.retrosheet_biofile",
    "biofile0.csv": "raw.retrosheet_biofile0",
    "coaches.csv": "raw.retrosheet_coach",
    "relatives.csv": "raw.retrosheet_relative",
}

BIODATA_MEMBERS = {
    "ballparks0.csv": "raw.retrosheet_ballpark",
    "coaches0.csv": "raw.retrosheet_coach0",
    "managers0.csv": "raw.retrosheet_manager",
    "teams0.csv": "raw.retrosheet_team0",
    "umpires0.csv": "raw.retrosheet_umpire",
}


def _park_codes() -> pd.DataFrame:
    path = manifest.download_required(
        SOURCE, "parkcode.txt", "https://www.retrosheet.org/parkcode.txt"
    )
    return pd.read_csv(path)


def _team_ids() -> pd.DataFrame:
    path = manifest.download_required(
        SOURCE, "TEAMABR.TXT", "https://www.retrosheet.org/TEAMABR.TXT"
    )
    return pd.read_csv(path, header=None, names=TEAM_FIELDS)


def _zip_tables(filename: str, url: str, members: dict[str, str]) -> dict[str, pd.DataFrame]:
    path = manifest.download_required(SOURCE, filename, url)
    tables = {}
    with zipfile.ZipFile(path) as zf:
        for member, table in members.items():
            with zf.open(member) as f:
                tables[table] = pd.read_csv(f, low_memory=False)
    manifest.mark_status(SOURCE, path.name, "loaded")
    return tables


def _biofile_tables() -> dict[str, pd.DataFrame]:
    return _zip_tables("biofile.zip", "https://www.retrosheet.org/biofile.zip", BIOFILE_MEMBERS)


def _biodata_tables() -> dict[str, pd.DataFrame]:
    return _zip_tables(
        "biodata.zip", "https://www.retrosheet.org/downloads/biodata.zip", BIODATA_MEMBERS
    )


def _run(conn: psycopg.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    counts["raw.retrosheet_park"] = load_dataframe(conn, "raw.retrosheet_park", _park_codes())
    manifest.mark_status(SOURCE, "parkcode.txt", "loaded")
    counts["raw.retrosheet_team"] = load_dataframe(conn, "raw.retrosheet_team", _team_ids())
    manifest.mark_status(SOURCE, "TEAMABR.TXT", "loaded")
    for table, df in _biofile_tables().items():
        counts[table] = load_dataframe(conn, table, df)
    for table, df in _biodata_tables().items():
        counts[table] = load_dataframe(conn, table, df)
    return counts


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
    return [
        check_table_has_rows("raw.retrosheet_park"),
        check_table_has_rows("raw.retrosheet_biofile"),
        check_last_run(SOURCE),
        check_recent_run(SOURCE, FRESHNESS_THRESHOLD_MINUTES),
    ]
