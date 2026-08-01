"""Lands Retrosheet's box-score-only files into raw.retrosheet_box_game/
batting/fielding/pitching/double/triple/homerun/stolenbase/doubleplay/
tripleplay/sacbunt, via the Chadwick `cwbox` CLI tool — closes the coverage
gap retrosheet_event.py documents but doesn't fill: pre-1910 seasons
(1898-1909, plus the 1871/1872/1874 NA seasons), and Negro League games
that only ever exist as box scores, never full play-by-play.

The seven supplementary per-event lists (double/triple/homerun/stolenbase/
doubleplay/tripleplay/sacbunt) were previously excluded entirely — cwbox's
`-X` output includes them (confirmed by generating real XML and inspecting
every top-level element it actually produces, not from documentation), but
`_parse_cwbox_xml` (chadwick_tools.py) only extracted game/batting/
fielding/pitching. Built now per explicit direction to ingest everything;
see docs/DECISIONS.md ADR-012 for the original exclusion note this
supersedes. Each has a real, sometimes-empty-per-year shape (e.g. a season
with no triple plays), which `load_dataframe`/`_load_archive` handle the
same way as any other genuinely-sparse table — no special-casing needed.

Source archives:
- 1871box.zip, 1872box.zip, 1874box.zip: individual pre-1898 NA seasons.
  Already bundle their own TEAM{year} and roster files.
- 1890sbox.zip (despite the name, covers 1898-1899 only), 1900sbox.zip
  (1900-1909): MLB box-score-only seasons. Bundle neither team nor roster
  files.
- allebr.zip: Negro League box scores, 1903-1961 (wider than
  retrosheet_event's Negro League play-by-play coverage of 1935-1949).
  Also bundles neither.

For archives missing team/roster files, cwbox refuses to run at all without
*a* TEAM{year} file present (same as cwevent/cwgame — see chadwick_tools.py),
but unlike those tools, an empty placeholder isn't enough: cwbox resolves
team codes/names FROM the team file, not from anything inside the box-score
file itself (confirmed by testing both ways against real data — see
docs/DECISIONS.md ADR-012). So a real one is constructed instead, from
Retrosheet's own official team registries — TEAMABR.TXT for MLB seasons,
biodata.zip's teams0.csv for Negro League seasons (already used elsewhere
in this project) — filtered to whichever teams were active in the year
being processed, in the exact format Retrosheet's own bundled TEAM{year}
files use (confirmed against a real one before relying on it:
"team_id,league,city,nickname" — see retrosheet.org/eventfile.htm). Real
roster files are pulled the same way, from Retrosheet's own rosters.zip
(already used by retrosheet_roster.py). This follows Retrosheet's own
documented requirement (retrosheet.org/datause.html: "you must have the
'team' and the appropriate roster files in the same directory"), not a
workaround around it.
"""

import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import psycopg

from mlb_baseball import chadwick_tools, manifest
from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_last_run, check_table_has_rows
from mlb_baseball.ingest import track_run
from mlb_baseball.load import load_dataframe

SOURCE = "retrosheet_box"
EVENTS_BASE_URL = "https://www.retrosheet.org/events"

GAME_TABLE = "raw.retrosheet_box_game"
BATTING_TABLE = "raw.retrosheet_box_batting"
FIELDING_TABLE = "raw.retrosheet_box_fielding"
PITCHING_TABLE = "raw.retrosheet_box_pitching"
# cwbox's seven supplementary per-event lists (doubles/triples/homeruns/
# stolen bases/double plays/triple plays/sac bunts) — confirmed present in
# real cwbox -X output and previously excluded entirely (see this module's
# original ADR-012 note and chadwick_tools.py's SUPPLEMENTARY_LISTS).
# tables dict key (from chadwick_tools.run_cwbox) -> raw table name.
SUPPLEMENTARY_TABLES = {
    "double": "raw.retrosheet_box_double",
    "triple": "raw.retrosheet_box_triple",
    "homerun": "raw.retrosheet_box_homerun",
    "stolenbase": "raw.retrosheet_box_stolenbase",
    "doubleplay": "raw.retrosheet_box_doubleplay",
    "tripleplay": "raw.retrosheet_box_tripleplay",
    "sacbunt": "raw.retrosheet_box_sacbunt",
}
# tables dict key -> raw table name, for every table run_cwbox returns.
TABLE_MAP = {
    "game": GAME_TABLE,
    "batting": BATTING_TABLE,
    "fielding": FIELDING_TABLE,
    "pitching": PITCHING_TABLE,
    **SUPPLEMENTARY_TABLES,
}
ALL_TABLES = list(TABLE_MAP.values())

# filename -> group. "na" archives already bundle their own team/roster
# files; "era"/"negro_league" archives need them constructed (see module
# docstring) using a different team registry each.
SELF_CONTAINED_ARCHIVES = {
    "1871box.zip": "na",
    "1872box.zip": "na",
    "1874box.zip": "na",
}
NEEDS_TEAM_FILE_ARCHIVES = {
    "1890sbox.zip": "era",  # 1898-1899, despite the "1890s" filename
    "1900sbox.zip": "era",  # 1900-1909
    "allebr.zip": "negro_league",
}

TEAM_FIELDS = ["team_id", "league", "city", "nickname", "first_year", "last_year"]


def _mlb_team_registry() -> pd.DataFrame:
    path = manifest.download_required(SOURCE, "TEAMABR.TXT", "https://www.retrosheet.org/TEAMABR.TXT")
    return pd.read_csv(path, header=None, names=TEAM_FIELDS)


def _negro_league_team_registry() -> pd.DataFrame:
    path = manifest.download_required(
        SOURCE, "biodata.zip", "https://www.retrosheet.org/downloads/biodata.zip"
    )
    with zipfile.ZipFile(path) as zf:
        with zf.open("teams0.csv") as f:
            df = pd.read_csv(f)
    df = df.rename(columns={"team": "team_id"})
    df["league"] = "NGL"  # teams0.csv itself carries no league column for these
    df["first_year"] = df["first_g"].astype(str).str[:4].astype(int)
    df["last_year"] = df["last_g"].astype(str).str[:4].astype(int)
    return df[TEAM_FIELDS]


def _team_registry(group: str) -> pd.DataFrame:
    return _negro_league_team_registry() if group == "negro_league" else _mlb_team_registry()


def _rosters_zip() -> Path:
    return manifest.download_required(SOURCE, "rosters.zip", "https://www.retrosheet.org/rosters.zip")


def _copy_matching_rosters(rosters_zip: Path, year: int, dest_dir: Path) -> None:
    with zipfile.ZipFile(rosters_zip) as zf:
        for name in zf.namelist():
            if name.endswith(".ROS") and chadwick_tools.year_of(name) == year:
                dest_dir.joinpath(name).write_bytes(zf.read(name))


def _prepare_team_file(
    year_dir: Path, year: int, registry: pd.DataFrame, rosters_zip: Path
) -> None:
    """No-op if the archive already bundled a real TEAM{year} (the "na"
    group). Otherwise builds one from `registry` and copies matching real
    roster files alongside it — see module docstring."""
    if (year_dir / f"TEAM{year}").exists():
        return
    active = registry[(registry["first_year"] <= year) & (year <= registry["last_year"])]
    teams = list(
        active[["team_id", "league", "city", "nickname"]].itertuples(index=False, name=None)
    )
    chadwick_tools.write_team_file(year_dir, year, teams)
    _copy_matching_rosters(rosters_zip, year, year_dir)


def _load_scope(year: int, group: str) -> str:
    return f"{year}_{group}"


def _parse_archive(archive_path: Path, group: str) -> dict[int, dict[str, pd.DataFrame]]:
    needs_team_file = group in {"era", "negro_league"}
    registry = _team_registry(group) if needs_team_file else None
    rosters_zip = _rosters_zip() if needs_team_file else None

    results: dict[int, dict[str, pd.DataFrame]] = {}
    with tempfile.TemporaryDirectory(prefix=f"retrosheet_box_{group}_") as tmp:
        extract_dir = Path(tmp)
        with zipfile.ZipFile(archive_path) as zf:
            zf.extractall(extract_dir)
        for year, year_dir in chadwick_tools.split_by_year(extract_dir).items():
            if needs_team_file:
                assert registry is not None and rosters_zip is not None
                _prepare_team_file(year_dir, year, registry, rosters_zip)
            tables = chadwick_tools.run_cwbox(year_dir, year)
            scope = _load_scope(year, group)
            for df in tables.values():
                df["_season"] = str(year)
                df["_group"] = group
                df["_scope"] = scope
            results[year] = tables
    return results


def _load_archive(
    conn: psycopg.Connection, filename: str, url: str, group: str, *, force: bool = False
) -> dict[str, int]:
    if not force and manifest.load_manifest(SOURCE).get(filename, {}).get("status") == "loaded":
        return {}
    archive_path = manifest.download(SOURCE, filename, url, force=force)
    if archive_path is None:
        return {}
    counts: dict[str, int] = dict.fromkeys(ALL_TABLES, 0)
    for tables in _parse_archive(archive_path, group).values():
        # game's own _scope stands in for the whole batch's scope value —
        # every table in `tables` was stamped with the same _scope in
        # _parse_archive. Supplementary tables (doubles/triples/etc.) can be
        # genuinely empty for a given year/group (e.g. no triple plays that
        # season) — load_dataframe handles an empty DataFrame fine (creates
        # the table with 0 rows, doesn't error), so no special-casing needed.
        scope_value = tables["game"]["_scope"].iloc[0]
        for key, raw_table in TABLE_MAP.items():
            df = tables[key]
            if df.empty:
                continue
            counts[raw_table] += load_dataframe(
                conn, raw_table, df, scope_column="_scope", scope_value=scope_value
            )
    manifest.mark_status(SOURCE, filename, "loaded")
    return counts


def bootstrap() -> dict[str, int]:
    totals: dict[str, int] = {}
    with get_connection() as conn, track_run(conn, SOURCE, "bootstrap") as result:
        all_archives = {**SELF_CONTAINED_ARCHIVES, **NEEDS_TEAM_FILE_ARCHIVES}
        for filename, group in all_archives.items():
            for table, count in _load_archive(
                conn, filename, f"{EVENTS_BASE_URL}/{filename}", group
            ).items():
                totals[table] = totals.get(table, 0) + count
            conn.commit()
        result["rows"] = sum(totals.values())
    return totals


def update() -> dict[str, int]:
    """All source archives here cover long-closed historical eras (the most
    recent, allebr.zip's Negro League coverage, ends 1961) — nothing new is
    ever published for these. update() re-runs the same full load, forcing
    past the "already loaded" skip bootstrap() relies on, in case Retrosheet
    ever corrects an archive in place; harmless and idempotent."""
    with get_connection() as conn, track_run(conn, SOURCE, "update") as result:
        totals: dict[str, int] = {}
        all_archives = {**SELF_CONTAINED_ARCHIVES, **NEEDS_TEAM_FILE_ARCHIVES}
        for filename, group in all_archives.items():
            for table, count in _load_archive(
                conn, filename, f"{EVENTS_BASE_URL}/{filename}", group, force=True
            ).items():
                totals[table] = totals.get(table, 0) + count
            conn.commit()
        result["rows"] = sum(totals.values())
    return totals


def health_check() -> list[Check]:
    missing = chadwick_tools.missing_tools()
    tool_check = (
        Check("chadwick tools (cwbox)", False, f"missing: {', '.join(missing)}")
        if missing
        else Check("chadwick tools (cwbox)", True, "cwbox found on PATH")
    )
    return [
        tool_check,
        *[check_table_has_rows(t) for t in ALL_TABLES],
        check_last_run(SOURCE),
    ]
