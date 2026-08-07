"""Lands Retrosheet's official pre-parsed CSV products into raw.retrosheet_*.

Source is retrosheet.org's own "CSV downloads" product (not the raw event
files, and not any third-party mirror) — one zip per year at
retrosheet.org/downloads/{year}/{year}csvs.zip, containing seven properly
headered CSVs: play-by-play (`plays`, 177 columns — richer than what the
cwevent CLI tool produces from the raw event files) plus per-game/per-player
`gameinfo`, `teamstats`, `batting`, `pitching`, `fielding`, and `allplayers`.
This replaced an earlier version of this connector that shelled out to
cwevent against a git clone of the raw event files. Raw event files are back
as a separate, additional product — see connectors/retrosheet_event.py — but
this CSV product stays too: it's the faster, simpler, pre-parsed path for
bootstrap speed and cross-validation. See docs/DECISIONS.md ADR-004 and the
ADR that added retrosheet_event.py alongside it.

Coverage is 1898-present for this product (narrower than the raw event
files' 1871+ — a real, documented gap, not glossed over).

Downloads land on disk first (downloads/retrosheet/, tracked in a JSON
manifest — see mlb_baseball/manifest.py) before parsing, so a bootstrap that
dies partway through doesn't force re-fetching years already downloaded.

Like Retrosheet's event files, this is too large to fully reload every run,
so each year is loaded independently via load_dataframe's scope_column —
see docs/ARCHITECTURE.md "Loading patterns". bootstrap() commits after each
year for the same reason the previous version did: a failure partway through
~128 years shouldn't lose already-loaded years, and each year's load is
independently idempotent.

bootstrap() fetches years sequentially, deliberately — an earlier version
used a bounded thread pool to overlap network I/O, but a real production run
against this exact code hung partway through (44 threads stuck in
futex_wait_queue, far more than the ~5 expected, with no proper profiler
available here to safely root-cause it). Reverted rather than keep debugging
a concurrency bug blind — see docs/DECISIONS.md ADR-005 and CLAUDE.md
"prefer explicit, boring code over cleverness."
"""

import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import psycopg

from mlb_baseball import manifest
from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_last_run, check_table_has_rows
from mlb_baseball.ingest import track_run
from mlb_baseball.load import load_dataframe

SOURCE = "retrosheet"
BASE_URL = "https://www.retrosheet.org/downloads"
FIRST_YEAR = 1898
CSV_NAMES = ["allplayers", "batting", "fielding", "gameinfo", "pitching", "plays", "teamstats"]


def _download_year(year: int) -> Path | None:
    filename = f"{year}csvs.zip"
    return manifest.download(SOURCE, filename, f"{BASE_URL}/{year}/{filename}")


def _extract_csvs(year: int, zip_path: Path) -> dict[str, pd.DataFrame]:
    dataframes = {}
    with zipfile.ZipFile(zip_path) as zf:
        for name in CSV_NAMES:
            with zf.open(f"{year}{name}.csv") as f:
                df = pd.read_csv(f, low_memory=False).copy()
                df["_season"] = str(year)
                dataframes[name] = df
    return dataframes


def _load_zip(conn: psycopg.Connection, year: int, zip_path: Path) -> dict[str, int]:
    counts = {}
    for name, df in _extract_csvs(year, zip_path).items():
        table = f"raw.retrosheet_{name}"
        counts[table] = load_dataframe(
            conn,
            table,
            df,
            scope_column="_season",
            scope_value=str(year),
            schema_drift_policy="error",
        )
    manifest.mark_status(SOURCE, zip_path.name, "loaded")
    return counts


def _load_year(conn: psycopg.Connection, year: int) -> dict[str, int]:
    zip_path = _download_year(year)
    if zip_path is None:
        return {}
    return _load_zip(conn, year, zip_path)


def bootstrap() -> dict[str, int]:
    totals: dict[str, int] = {}
    with get_connection() as conn, track_run(conn, SOURCE, "bootstrap") as result:
        for year in range(FIRST_YEAR, date.today().year + 1):
            for table, count in _load_year(conn, year).items():
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
    """Retrosheet's own data has a real inconsistency here — one row
    (HOM193508100, a 1935 Homestead Grays game) has gametype "Regular"
    alongside "regular" everywhere else. Raw stays source-faithful (no
    silent cleanup) — this check exists to keep that real quirk visible,
    not to demand it go away. It's not a live risk: conform.py's
    _build_games() normalizes casing with lower() when building
    core.game.game_type, specifically because of what this check found, so
    a case-sensitive `WHERE game_type = 'regular'` downstream doesn't
    silently miss this game. Reports ok=True either way — the thing worth
    knowing is the quirk's existence and count, not treating a single
    90-year-old data point as an ongoing failure once it's handled."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT gametype FROM raw.retrosheet_gameinfo")
            values = {row[0] for row in cur.fetchall() if row[0] is not None}
    lowered = {v.lower() for v in values}
    if len(lowered) != len(values):
        return Check(
            "retrosheet gametype casing",
            True,
            f"inconsistent casing in raw (expected, normalized in core.game): {sorted(values)}",
        )
    return Check("retrosheet gametype casing", True, f"{len(values)} distinct values, consistent")


def health_check() -> list[Check]:
    return [
        check_table_has_rows("raw.retrosheet_plays"),
        check_last_run(SOURCE),
        _check_gametype_casing(),
    ]
