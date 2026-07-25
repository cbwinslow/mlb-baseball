"""Lands Retrosheet's official pre-parsed CSV products into raw.retrosheet_*.

Source is retrosheet.org's own "CSV downloads" product (not the raw event
files, and not any third-party mirror) — one zip per year at
retrosheet.org/downloads/{year}/{year}csvs.zip, containing seven properly
headered CSVs: play-by-play (`plays`, 177 columns — richer than what the
cwevent CLI tool produces from the raw event files) plus per-game/per-player
`gameinfo`, `teamstats`, `batting`, `pitching`, `fielding`, and `allplayers`.
This replaced an earlier version of this connector that shelled out to
cwevent against a git clone of the raw event files — abandoned once this
richer, simpler, more authoritative official source was found (no CLI tool
or 2.5GB git clone needed, just a small HTTP download and pandas.read_csv).
See docs/DECISIONS.md.

Coverage is 1898-present for this product (narrower than the raw event
files' 1871+ — a real, documented gap, not glossed over).

Like Retrosheet's event files, this is too large to fully reload every run,
so each year is loaded independently via load_dataframe's scope_column —
see docs/ARCHITECTURE.md "Loading patterns". bootstrap() commits after each
year for the same reason the previous version did: a failure partway through
~128 years shouldn't lose already-loaded years, and each year's load is
independently idempotent.

bootstrap() fetches years concurrently (network is the actual bottleneck —
128 sequential HTTP round-trips) via a bounded thread pool, but still writes
to Postgres sequentially, one year at a time, in order. MAX_WORKERS is
deliberately modest: retrosheet.org is a small, volunteer-run site, not a
CDN-backed API — this should be fast for us without looking like a scraper
hammering their server.
"""

import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pandas as pd
import psycopg
import requests

from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_last_run, check_table_has_rows
from mlb_baseball.ingest import track_run
from mlb_baseball.load import load_dataframe

SOURCE = "retrosheet"
BASE_URL = "https://www.retrosheet.org/downloads"
FIRST_YEAR = 1898
MAX_WORKERS = 4
CSV_NAMES = ["allplayers", "batting", "fielding", "gameinfo", "pitching", "plays", "teamstats"]


def _fetch_year_zip(year: int) -> bytes | None:
    response = requests.get(f"{BASE_URL}/{year}/{year}csvs.zip", timeout=60)
    if response.status_code == 404:
        return None  # e.g. the current, still-in-progress season
    response.raise_for_status()
    return response.content


def _extract_csvs(year: int, zip_bytes: bytes) -> dict[str, pd.DataFrame]:
    dataframes = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in CSV_NAMES:
            with zf.open(f"{year}{name}.csv") as f:
                df = pd.read_csv(f, low_memory=False).copy()
                df["_season"] = str(year)
                dataframes[name] = df
    return dataframes


def _load_zip(conn: psycopg.Connection, year: int, zip_bytes: bytes) -> dict[str, int]:
    counts = {}
    for name, df in _extract_csvs(year, zip_bytes).items():
        table = f"raw.retrosheet_{name}"
        counts[table] = load_dataframe(
            conn, table, df, scope_column="_season", scope_value=str(year)
        )
    return counts


def _load_year(conn: psycopg.Connection, year: int) -> dict[str, int]:
    zip_bytes = _fetch_year_zip(year)
    if zip_bytes is None:
        return {}
    return _load_zip(conn, year, zip_bytes)


def bootstrap() -> dict[str, int]:
    totals: dict[str, int] = {}
    years = list(range(FIRST_YEAR, date.today().year + 1))
    with get_connection() as conn, track_run(conn, SOURCE, "bootstrap") as result:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # executor.map keeps MAX_WORKERS fetches in flight and yields in
            # order as we consume it, overlapping network wait for upcoming
            # years with DB writes for the current one — without holding all
            # ~128 years' zips in memory at once.
            for year, zip_bytes in zip(years, executor.map(_fetch_year_zip, years), strict=True):
                if zip_bytes is None:
                    continue
                for table, count in _load_zip(conn, year, zip_bytes).items():
                    totals[table] = totals.get(table, 0) + count
                conn.commit()
        result["rows"] = sum(totals.values())
    return totals


def update() -> dict[str, int]:
    with get_connection() as conn, track_run(conn, SOURCE, "update") as result:
        totals = _load_year(conn, date.today().year)
        conn.commit()
        result["rows"] = sum(totals.values())
    return totals


def _check_gametype_casing() -> Check:
    """Retrosheet's own data has a real inconsistency here — one row was found
    with gametype "Regular" alongside "regular" everywhere else. Raw stays
    source-faithful (no silent cleanup), but doctor should flag it so it's
    visible rather than a surprise later in the conformed layer."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT gametype FROM raw.retrosheet_gameinfo")
            values = {row[0] for row in cur.fetchall() if row[0] is not None}
    lowered = {v.lower() for v in values}
    if len(lowered) != len(values):
        return Check("retrosheet gametype casing", False, f"inconsistent casing: {sorted(values)}")
    return Check("retrosheet gametype casing", True, f"{len(values)} distinct values, consistent")


def health_check() -> list[Check]:
    return [
        check_table_has_rows("raw.retrosheet_plays"),
        check_last_run(SOURCE),
        _check_gametype_casing(),
    ]
