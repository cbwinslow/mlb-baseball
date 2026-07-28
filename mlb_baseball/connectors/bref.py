"""Lands Baseball-Reference's season-level batting/pitching stats into
raw.bref_batting/raw.bref_pitching, via pybaseball.batting_stats_bref()/
pitching_stats_bref() (already a project dependency).

FIRST_YEAR = 2008 — a hard constraint in pybaseball itself, not a scoping
choice made here: batting_stats_range()/pitching_stats_range() (which these
two functions call internally) raise ValueError("Year must be 2008 or
later") for anything earlier, confirmed by reading the library's source
(mlb_baseball/connectors/bref.py's own testing didn't need to rediscover
this — it's an explicit, deliberate check in pybaseball's own code).

This is Baseball-Reference, not FanGraphs — confirmed these are two
different scrape targets in pybaseball with two different outcomes when
tested directly in this environment:
- `pybaseball.batting_stats()`/`pitching_stats()` (FanGraphs) — confirmed
  BROKEN: fangraphs.com now sits behind Cloudflare and returns a hard
  HTTP 403 to pybaseball's scraper (reproduced directly: `HTTPError: Error
  accessing 'https://www.fangraphs.com/leaders-legacy.aspx'. Received
  status code 403`). Not attempted here — see docs/DATA_SOURCES.md's
  Deferred section for the confirmed failure.
- `pybaseball.batting_stats_bref()`/`pitching_stats_bref()`
  (baseball-reference.com) — confirmed WORKING, reproduced directly with
  real data returned for 2025.
- `pybaseball.team_batting_bref()`/`team_pitching_bref()` — confirmed
  BROKEN in the installed pybaseball version (raises `IndexError: list
  index out of range` on a real call). Not built here; team-season
  aggregates are derivable from our own core layer once conform.py runs
  (core.play/core.pitch), same reasoning as the Statcast/MLB-API
  leaderboards documented as low-priority in statcast_leaderboard.py.

One HTTP request per season per stat type (confirmed via reading
batting_stats_range()'s implementation — a single date-range page fetch,
not paginated per day), so a full 2008-present bootstrap is ~36 requests
total — no weekly-chunk batching needed, unlike statcast.py.

bootstrap() loads full history one season at a time; update() reloads just
the current season (season-scoped replace, idempotent). Not on a repeating
cron schedule — season stats don't change intra-day — so health_check()
uses check_last_run, not check_recent_run, same as statcast.py.
"""

from datetime import date

import psycopg
import pybaseball

from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_last_run, check_table_has_rows
from mlb_baseball.ingest import track_run
from mlb_baseball.load import load_dataframe, season_already_loaded
from mlb_baseball.net import call_with_retry

SOURCE = "bref"
FIRST_YEAR = 2008
TABLES = [
    ("raw.bref_batting", pybaseball.batting_stats_bref),
    ("raw.bref_pitching", pybaseball.pitching_stats_bref),
]


def _load_table(conn: psycopg.Connection, table: str, fn, season: int) -> int:
    df = call_with_retry(fn, season)
    if df.empty:
        return 0
    df["_season"] = str(season)
    return load_dataframe(conn, table, df, scope_column="_season", scope_value=str(season))


def _load_season(conn: psycopg.Connection, season: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table, fn in TABLES:
        try:
            counts[table] = _load_table(conn, table, fn, season)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"bref: {table} {season} failed ({exc}); skipping")
            counts[table] = 0
    return counts


def bootstrap() -> dict[str, int]:
    current_year = date.today().year
    totals: dict[str, int] = {}
    with get_connection() as conn, track_run(conn, SOURCE, "bootstrap") as result:
        for season in range(FIRST_YEAR, current_year + 1):
            if season < current_year and season_already_loaded(conn, "raw.bref_batting", season):
                print(f"bref: {season} already loaded, skipping")
                continue
            for table, count in _load_season(conn, season).items():
                totals[table] = totals.get(table, 0) + count
        result["rows"] = sum(totals.values())
    return totals


def update() -> dict[str, int]:
    with get_connection() as conn, track_run(conn, SOURCE, "update") as result:
        totals = _load_season(conn, date.today().year)
        result["rows"] = sum(totals.values())
    return totals


def health_check() -> list[Check]:
    return [
        check_table_has_rows("raw.bref_batting"),
        check_table_has_rows("raw.bref_pitching"),
        check_last_run(SOURCE),
    ]
