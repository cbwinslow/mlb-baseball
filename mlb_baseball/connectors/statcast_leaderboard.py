"""Lands Baseball Savant's season-level tracking leaderboards — the pybaseball
functions that use genuinely different raw inputs (fielder positioning, hang
time, throw-to-base timing) than the pitch-level `statcast()` pull already
covered by statcast.py. Confirmed via direct inspection of pybaseball's own
source and a live call per function that these are NOT derivable from
raw.statcast_pitch — that table has no fielder-position or baserunning data
at all, only pitch/batted-ball events.

FIRST_YEAR = 2015 (confirmed via direct testing: statcast_sprint_speed(2014)
returns 0 rows, statcast_sprint_speed(2015) returns 550 — matches statcast.py's
own documented PITCHf/x-vs-Statcast era boundary; these leaderboards simply
don't exist before full Trackman/Statcast tracking went live league-wide).

One raw table per leaderboard, one API call per season per leaderboard
(these are season aggregates, not per-game/per-week data, so no need for
statcast.py's weekly-chunk batching):
- raw.statcast_sprint_speed — statcast_sprint_speed()
- raw.statcast_poptime — statcast_catcher_poptime()
- raw.statcast_framing — statcast_catcher_framing()
- raw.statcast_jump — statcast_outfielder_jump()
- raw.statcast_oaa — statcast_outs_above_average(), looped over fielding
  positions 3B/4/2B/5/SS/6/3B... (numeric position codes 3,4,5,6,7,8,9;
  catcher/2 explicitly excluded — the library itself raises ValueError for
  it, confirmed by reading pybaseball's source: "This particular leaderboard
  does not include catchers"). Only the default view="Fielder" perspective
  is pulled (not Pitcher/Fielding_Team/Batter/Batting_Team) — that's the
  standard "player X had Y outs above average" stat; the other views are
  team- or pitcher-level aggregates, a materially larger scope not requested.
- raw.statcast_catch_prob — statcast_outfield_catch_prob()
- raw.statcast_oaa_direction — statcast_outfield_directional_oaa()
- raw.statcast_running_split — statcast_running_splits()

Not built: `statcast_batter_exitvelo_barrels`/`_expected_stats`/
`_percentile_ranks`/`_pitch_arsenal` and the pitcher equivalents —
confirmed these are computable from raw.statcast_pitch/core.pitch once
conform.py runs (they're aggregates over pitch-level data we already have
in full), not a new raw input like the leaderboards above.

bootstrap() loads full history one season at a time per leaderboard;
update() reloads just the current season. Not on a repeating cron schedule
(same reasoning as statcast.py — this data isn't real-time and doesn't
change once a season's data is published), so health_check() uses
check_last_run, not check_recent_run.
"""

import io
from datetime import date

import pandas as pd
import psycopg
import pybaseball
import requests

from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_last_run, check_table_has_rows
from mlb_baseball.ingest import track_run
from mlb_baseball.load import load_dataframe, season_already_loaded
from mlb_baseball.net import call_with_retry

SOURCE = "statcast_leaderboard"
FIRST_YEAR = 2015
OAA_POSITIONS = [3, 4, 5, 6, 7, 8, 9]
# pybaseball's own statcast_catcher_framing() (installed version) still
# calls baseballsavant.mlb.com/catcher_framing?...csv=true, which Savant has
# since moved off — confirmed directly: that URL now returns the ordinary
# HTML leaderboard page (HTTP 200, real page title, not a Cloudflare block)
# regardless of csv=true, which is what caused pandas' "Expected 1 fields...
# saw 4" parse error (it was parsing HTML as CSV). The leaderboard itself
# moved to /leaderboard/catcher-framing, confirmed to return real CSV there
# — fetched directly here rather than through the broken library function.
FRAMING_URL = "https://baseballsavant.mlb.com/leaderboard/catcher-framing"


def _fetch_framing(year: int) -> pd.DataFrame:
    res = requests.get(FRAMING_URL, params={"year": year, "team": "", "min": "q", "csv": "true"})
    res.raise_for_status()
    return pd.read_csv(io.StringIO(res.content.decode("utf-8")))


# (raw table, callable) for every leaderboard that's a single call per
# season — raw.statcast_oaa is handled separately below since it needs a
# position loop.
SIMPLE_LEADERBOARDS = [
    ("raw.statcast_sprint_speed", pybaseball.statcast_sprint_speed),
    ("raw.statcast_poptime", pybaseball.statcast_catcher_poptime),
    ("raw.statcast_framing", _fetch_framing),
    ("raw.statcast_jump", pybaseball.statcast_outfielder_jump),
    ("raw.statcast_catch_prob", pybaseball.statcast_outfield_catch_prob),
    ("raw.statcast_oaa_direction", pybaseball.statcast_outfield_directional_oaa),
    ("raw.statcast_running_split", pybaseball.statcast_running_splits),
]


def _load_simple_leaderboard(conn: psycopg.Connection, table: str, fn, season: int) -> int:
    df = call_with_retry(fn, season)
    if df.empty:
        return 0
    df["_season"] = str(season)
    return load_dataframe(conn, table, df, scope_column="_season", scope_value=str(season))


def _load_oaa(conn: psycopg.Connection, season: int) -> int:
    total = 0
    for pos in OAA_POSITIONS:
        df = call_with_retry(pybaseball.statcast_outs_above_average, season, pos)
        if df.empty:
            continue
        scope = f"{season}_{pos}"
        df["_season"] = str(season)
        df["_scope"] = scope
        total += load_dataframe(
            conn, "raw.statcast_oaa", df, scope_column="_scope", scope_value=scope
        )
    return total


def _load_season(conn: psycopg.Connection, season: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table, fn in SIMPLE_LEADERBOARDS:
        try:
            counts[table] = _load_simple_leaderboard(conn, table, fn, season)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"statcast_leaderboard: {table} {season} failed ({exc}); skipping")
            counts[table] = 0
    try:
        counts["raw.statcast_oaa"] = _load_oaa(conn, season)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        print(f"statcast_leaderboard: raw.statcast_oaa {season} failed ({exc}); skipping")
        counts["raw.statcast_oaa"] = 0
    return counts


def bootstrap() -> dict[str, int]:
    current_year = date.today().year
    totals: dict[str, int] = {}
    with get_connection() as conn, track_run(conn, SOURCE, "bootstrap") as result:
        for season in range(FIRST_YEAR, current_year + 1):
            # Past seasons are published and complete — skip re-fetching on
            # a bootstrap re-run, same reasoning as statcast.py/mlb_api.py.
            # raw.statcast_sprint_speed is the completeness proxy for the
            # whole season's leaderboard set (first table in the loop).
            if season < current_year and season_already_loaded(
                conn, "raw.statcast_sprint_speed", season
            ):
                print(f"statcast_leaderboard: {season} already loaded, skipping")
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
        check_table_has_rows("raw.statcast_sprint_speed"),
        check_table_has_rows("raw.statcast_poptime"),
        check_table_has_rows("raw.statcast_framing"),
        check_table_has_rows("raw.statcast_jump"),
        check_table_has_rows("raw.statcast_oaa"),
        check_table_has_rows("raw.statcast_catch_prob"),
        check_table_has_rows("raw.statcast_oaa_direction"),
        check_table_has_rows("raw.statcast_running_split"),
        check_last_run(SOURCE),
    ]
