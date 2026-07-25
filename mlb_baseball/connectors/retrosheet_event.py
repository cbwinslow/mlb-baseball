"""Lands Retrosheet's raw play-by-play event files into raw.retrosheet_event
(per-play, via cwevent) and raw.retrosheet_game (per-game, via cwgame) — the
source-of-record Retrosheet product, distinct from and complementary to the
pre-parsed CSV product in retrosheet.py (see docs/DECISIONS.md). Both are
kept: the CSV product is faster to bootstrap from and useful for
cross-checking, but raw event files are what Retrosheet itself treats as
authoritative, and re-parsing them locally means this platform isn't
permanently downstream of retrosheet.org's own CSV-generation choices.

Coverage: full play-by-play 1910-2025 (plus 1914-1915 Federal League), with
some seasons partly or fully "deduced" from newspaper accounts/box scores
where the real record is missing (1910-1911, 1913-1959, 1962-1968) — same
record format, same parsing tools, not currently flagged separately in the
raw layer (a known, documented gap — see chadwick_tools.py). Also covers
post-season (1903-2025), All-Star games (1933-2025, no 1945/2020), and Negro
League play-by-play (1935-1949 plus notable pre-1937 games).

NOT covered by this connector: box-score-only event files (pre-1910, plus
the 1871/1872/1874 NA seasons, and Negro League box scores). Those use a
different file format (.EBA/.EBN) and Retrosheet's cwbox tool, which has an
incompatible CLI (no CSV/field-list output, only text/XML box scores) — a
real, separate parsing problem, not yet built. Tracked as a follow-up rather
than silently skipped.

Retrosheet bundles most of these as multi-year archives (e.g.
events/1910seve.zip covers all of 1910-1919 in one flat zip, event/roster/
team files for every year mixed together). cwevent/cwgame must be run one
year at a time — the -y flag governs which TEAM{year}/{team}{year}.ROS files
they look for — so each archive is extracted to a temp directory and split
into per-year subdirectories before parsing (_split_by_year). The downloaded
archive itself is what's kept on disk (via manifest.download, small: a few
hundred MB across the whole corpus); extraction is transient and cleaned up
after each load so it doesn't multiply that footprint.
"""

import re
import shutil
import tempfile
import zipfile
from datetime import date
from pathlib import Path

import psycopg

from mlb_baseball import chadwick_tools, manifest
from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_last_run, check_table_has_rows
from mlb_baseball.ingest import track_run
from mlb_baseball.load import load_dataframe

SOURCE = "retrosheet_event"
BASE_URL = "https://www.retrosheet.org/events"
EVENT_TABLE = "raw.retrosheet_event"
GAME_TABLE = "raw.retrosheet_game"

# Multi-year archives to bootstrap. Each covers the listed year range; the
# current decade also gets re-fetched (force=True) on update() since
# Retrosheet appends/corrects the current season in place.
PBP_DECADE_ARCHIVES = {
    "1910seve.zip": range(1910, 1920),
    "1920seve.zip": range(1920, 1930),
    "1930seve.zip": range(1930, 1940),
    "1940seve.zip": range(1940, 1950),
    "1950seve.zip": range(1950, 1960),
    "1960seve.zip": range(1960, 1970),
    "1970seve.zip": range(1970, 1980),
    "1980seve.zip": range(1980, 1990),
    "1990seve.zip": range(1990, 2000),
    "2000seve.zip": range(2000, 2010),
    "2010seve.zip": range(2010, 2020),
    "2020seve.zip": range(2020, date.today().year + 1),
}
SPECIAL_ARCHIVES = {
    "allpost.zip": "postseason",
    "allas.zip": "allstar",
    "allevr.zip": "negro_league",
}
CURRENT_DECADE_ARCHIVE = "2020seve.zip"

# Tried in order. A naive "first 4 digits anywhere" scan is ambiguous for
# team codes ending in a digit (e.g. "WS1") glued directly to a year, e.g.
# "WS11910.ROS" contains a run of 5 consecutive digits ("11910").
_YEAR_PATTERNS = [
    re.compile(r"^(\d{4})"),  # event/deduced files: 1910BOS.EVA, 1910.EDA
    re.compile(r"^TEAM(\d{4})$"),  # TEAM1910
    re.compile(r"(\d{4})\.ROS$"),  # roster files: BOS1910.ROS, WS11910.ROS
]


def _year_of(filename: str) -> int | None:
    for pattern in _YEAR_PATTERNS:
        match = pattern.search(filename)
        if match:
            return int(match.group(1))
    return None


def _split_by_year(extract_dir: Path) -> dict[int, Path]:
    """Reorganizes a flat, multi-year archive's extracted contents into
    per-year subdirectories (each self-contained: that year's event files
    plus its TEAM{year}/{team}{year}.ROS files), matching the shape
    chadwick_tools expects.

    Not every archive bundles team/roster files — the Negro League PBP
    archive (allevr.zip) is just one whole-league {year}.EVR file per year,
    no TEAM{year}/.ROS files at all (confirmed against the real downloaded
    archive: 37 files total, all .EVR, zero TEAM/ROS files). cwevent/cwgame
    both refuse to run without *a* team file present, even though they don't
    need it to produce correct output for a file with no team-level info to
    resolve — confirmed empty output is identical either way. So an empty
    placeholder is created for any year missing one, rather than skipping
    (and silently dropping) those years."""
    year_dirs: dict[int, Path] = {}
    for f in extract_dir.iterdir():
        if not f.is_file():
            continue
        year = _year_of(f.name)
        if year is None:
            continue
        year_dir = extract_dir / "by_year" / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, year_dir / f.name)
        year_dirs[year] = year_dir
    for year, year_dir in year_dirs.items():
        team_file = year_dir / f"TEAM{year}"
        if not team_file.exists():
            team_file.touch()
    return year_dirs


def _load_scope(year: int, group: str) -> str:
    return f"{year}_{group}"


def _parse_archive(archive_path: Path, group: str) -> dict[int, tuple]:
    """Extracts archive_path to a temp dir, splits by year, and runs
    cwevent+cwgame for every year present. Returns {year: (event_df, game_df)}.

    Tags each DataFrame with both _season (the real year, for querying) and
    _scope (year+group combined, e.g. "2024_pbp" vs "2024_postseason" — used
    as load_dataframe's scope_column). These must NOT be the same column:
    multiple archives can independently cover the same season (a regular-
    season decade zip, the post-season zip, the all-star zip, and the Negro
    League zip can all have rows for 1943), and scoping the replace on
    _season alone means loading a later archive for a year already covered
    by an earlier one would DELETE the earlier archive's rows before
    inserting its own — which is exactly what happened in a real run before
    this was caught (post-season/all-star/Negro League archives, processed
    after the regular-season decades, silently wiped ~16M regular-season
    rows down to just their own much smaller row counts)."""
    results: dict[int, tuple] = {}
    with tempfile.TemporaryDirectory(prefix=f"retrosheet_event_{group}_") as tmp:
        extract_dir = Path(tmp)
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(extract_dir)
        for year, year_dir in _split_by_year(extract_dir).items():
            scope = _load_scope(year, group)
            event_df = chadwick_tools.run_cwevent(year_dir, year)
            event_df["_season"] = str(year)
            event_df["_group"] = group
            event_df["_scope"] = scope
            game_df = chadwick_tools.run_cwgame(year_dir, year)
            game_df["_season"] = str(year)
            game_df["_group"] = group
            game_df["_scope"] = scope
            results[year] = (event_df, game_df)
    return results


def _load_archive(
    conn: psycopg.Connection, filename: str, url: str, group: str, *, force: bool = False
) -> dict[str, int]:
    # Resuming a bootstrap that failed partway through (e.g. a parser bug
    # hit on one archive) shouldn't force every already-loaded archive
    # through cwevent/cwgame again — that's real time on a full historical
    # run. force=True (used by update()) always bypasses this.
    if not force and manifest.load_manifest(SOURCE).get(filename, {}).get("status") == "loaded":
        return {}
    archive_path = manifest.download(SOURCE, filename, url, force=force)
    if archive_path is None:
        return {}
    counts: dict[str, int] = {EVENT_TABLE: 0, GAME_TABLE: 0}
    for event_df, game_df in _parse_archive(archive_path, group).values():
        counts[EVENT_TABLE] += load_dataframe(
            conn,
            EVENT_TABLE,
            event_df,
            scope_column="_scope",
            scope_value=event_df["_scope"].iloc[0],
        )
        counts[GAME_TABLE] += load_dataframe(
            conn,
            GAME_TABLE,
            game_df,
            scope_column="_scope",
            scope_value=game_df["_scope"].iloc[0],
        )
    manifest.mark_status(SOURCE, filename, "loaded")
    return counts


def bootstrap() -> dict[str, int]:
    totals: dict[str, int] = {}
    with get_connection() as conn, track_run(conn, SOURCE, "bootstrap") as result:
        for filename in PBP_DECADE_ARCHIVES:
            for table, count in _load_archive(
                conn, filename, f"{BASE_URL}/{filename}", "pbp"
            ).items():
                totals[table] = totals.get(table, 0) + count
            conn.commit()
        for filename, group in SPECIAL_ARCHIVES.items():
            for table, count in _load_archive(
                conn, filename, f"{BASE_URL}/{filename}", group
            ).items():
                totals[table] = totals.get(table, 0) + count
            conn.commit()
        result["rows"] = sum(totals.values())
    return totals


def update() -> dict[str, int]:
    """Re-fetches the current decade's archive (force=True — Retrosheet
    appends/corrects the current season in place) plus post-season/all-star,
    which also grow every year."""
    with get_connection() as conn, track_run(conn, SOURCE, "update") as result:
        totals: dict[str, int] = {}
        for filename, group in {
            CURRENT_DECADE_ARCHIVE: "pbp",
            "allpost.zip": "postseason",
            "allas.zip": "allstar",
        }.items():
            for table, count in _load_archive(
                conn, filename, f"{BASE_URL}/{filename}", group, force=True
            ).items():
                totals[table] = totals.get(table, 0) + count
            conn.commit()
        result["rows"] = sum(totals.values())
    return totals


def health_check() -> list[Check]:
    return [
        check_table_has_rows(EVENT_TABLE),
        check_table_has_rows(GAME_TABLE),
        check_last_run(SOURCE),
    ]
