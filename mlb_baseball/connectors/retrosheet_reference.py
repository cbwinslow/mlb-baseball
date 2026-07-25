"""Lands Retrosheet's reference/dimension files into raw.retrosheet_*: ballpark
codes, team ID history, and biographical/coaching/relatives data. All are
static whole-file downloads (not per-year), so bootstrap() and update() are
the same full-reload operation — like the Chadwick register and Lahman.

- Park codes: retrosheet.org/parkcode.txt — already headered CSV.
- Team ID history: retrosheet.org/TEAMABR.TXT — headerless; layout (6 fields:
  team ID, league, city, nickname, first year, last year) confirmed against
  TeamIDs.htm and verified against the real downloaded file before hardcoding.
- Biographical data: retrosheet.org/biofile.zip, containing four already-
  headered CSVs (biofile.csv, biofile0.csv — two different schemas Retrosheet
  distributes side by side, both landed as-is since raw stays source-faithful;
  coaches.csv; relatives.csv).
"""

import io
import zipfile

import pandas as pd
import psycopg
import requests

from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_last_run, check_table_has_rows
from mlb_baseball.ingest import track_run
from mlb_baseball.load import load_dataframe

SOURCE = "retrosheet_reference"
TEAM_FIELDS = ["team_id", "league", "city", "nickname", "first_year", "last_year"]

BIOFILE_MEMBERS = {
    "biofile.csv": "raw.retrosheet_biofile",
    "biofile0.csv": "raw.retrosheet_biofile0",
    "coaches.csv": "raw.retrosheet_coach",
    "relatives.csv": "raw.retrosheet_relative",
}


def _fetch_text(url: str) -> str:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def _fetch_bytes(url: str) -> bytes:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def _park_codes() -> pd.DataFrame:
    text = _fetch_text("https://www.retrosheet.org/parkcode.txt")
    return pd.read_csv(io.StringIO(text))


def _team_ids() -> pd.DataFrame:
    text = _fetch_text("https://www.retrosheet.org/TEAMABR.TXT")
    return pd.read_csv(io.StringIO(text), header=None, names=TEAM_FIELDS)


def _biofile_tables() -> dict[str, pd.DataFrame]:
    zip_bytes = _fetch_bytes("https://www.retrosheet.org/biofile.zip")
    tables = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for member, table in BIOFILE_MEMBERS.items():
            with zf.open(member) as f:
                tables[table] = pd.read_csv(f, low_memory=False)
    return tables


def _run(conn: psycopg.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    counts["raw.retrosheet_park"] = load_dataframe(conn, "raw.retrosheet_park", _park_codes())
    counts["raw.retrosheet_team"] = load_dataframe(conn, "raw.retrosheet_team", _team_ids())
    for table, df in _biofile_tables().items():
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
    ]
