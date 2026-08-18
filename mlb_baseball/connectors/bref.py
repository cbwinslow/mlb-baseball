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

`raw.bref_war_batting`/`raw.bref_war_pitching` — Baseball-Reference's own
WAR calculation (`bwar_bat()`/`bwar_pitch()`), not available from any other
source in this pipeline (Lahman has no WAR column; MLB Stats API doesn't
compute it either) — confirmed working directly: 126,418 batting rows and
57,686 pitching rows, full history back to 1871. Unlike the season-scoped
functions above, these two return the ENTIRE history in one call (no year
parameter exists) straight from Baseball-Reference's own published
war_daily_bat/war_daily_pitch tables — so they're loaded as a single full
reload every bootstrap()/update() run, not iterated per season, same
pattern as `chadwick_register.py`/`retrosheet_reference.py`.

Also evaluated directly, from pybaseball, and NOT built here:
- `top_prospects()` — confirmed BROKEN: raises
  `FileNotFoundError` because pybaseball's own scraper feeds a raw HTML
  response into a call that expects a file path (a bug in the installed
  library, not a network/auth issue) — same exclusion class as FanGraphs.
- `batting_stats_range()`/`pitching_stats_range()` — confirmed working,
  but this is an arbitrary-date-window slice of the same underlying
  Baseball-Reference stats `batting_stats_bref()`/`pitching_stats_bref()`
  already pull at season granularity; there's no natural way to "bootstrap"
  every possible date range, and any specific range a future analysis needs
  is already reconstructable from `core.play`/`core.pitch` plus the
  season-level bref tables.
- `get_splits()` — confirmed working (situational splits: vs. LHP/RHP,
  home/road, etc.), but it takes one player + one year per call with no
  bulk/leaderboard form — a full backfill would mean ~20,000 people ×
  up to ~18 years each, a combinatorial cost out of proportion to the
  value, the same reasoning ADR-020 already used to exclude full awards-
  recipient history.

One HTTP request per season per stat type (confirmed via reading
batting_stats_range()'s implementation — a single date-range page fetch,
not paginated per day), so a full 2008-present bootstrap is ~36 requests
total — no weekly-chunk batching needed, unlike statcast.py.

bootstrap() loads full history one season at a time (plus the WAR tables'
one-shot full reload); update() reloads just the current season (season-
scoped replace, idempotent) plus re-runs the same WAR full reload (cheap —
one HTTP call each, and idempotent by construction). Not on a repeating
cron schedule — season stats don't change intra-day — so health_check()
reports the outcome of the last run rather than treating a valid load as stale.
"""

from datetime import date

import psycopg
import pybaseball

from mlb_baseball.db import get_connection
from mlb_baseball.health import (
    Check,
    check_last_run,
    check_table_has_rows,
)
from mlb_baseball.ingest import track_run
from mlb_baseball.load import load_dataframe, season_already_loaded
from mlb_baseball.net import call_with_retry

SOURCE = "bref"
FIRST_YEAR = 2008
TABLES = [
    ("raw.bref_batting", pybaseball.batting_stats_bref),
    ("raw.bref_pitching", pybaseball.pitching_stats_bref),
]
# Full-history-in-one-call tables — no season parameter exists, so these are
# a whole-table replace every run rather than a per-season loop. See module
# docstring.
WAR_TABLES = [
    ("raw.bref_war_batting", pybaseball.bwar_bat),
    ("raw.bref_war_pitching", pybaseball.bwar_pitch),
]


def _repair_name_mojibake(name: object) -> object:
    """pybaseball.batting_stats_bref()/pitching_stats_bref() scrape HTML via
    get_soup() (pybaseball/league_batting_stats.py, league_pitching_stats.py),
    which has a real upstream bug on the response-decoding line: `s =
    str(session.get(url).content).encode()` calls Python's str() directly on
    a bytes object, which produces bytes.__repr__() text (e.g. the 11 real
    bytes b'Jos\\xc3\\xa9 Abreu' become the 17-character *literal* string
    "Jos\\xc3\\xa9 Abreu", backslashes and all) instead of decoding it --
    BeautifulSoup then parses that repr text as if it were the real page, so
    every accented player name comes back mangled instead of real UTF-8.
    Confirmed directly, not guessed: reproduced byte-for-byte with real bref
    data (both raw.bref_batting and raw.bref_pitching, ~9% of a season's
    names affected) and by reading pybaseball's own source for the exact
    str()/encode() line responsible (see issue #6). pybaseball's own
    bwar_bat()/bwar_pitch() (raw.bref_war_batting/raw.bref_war_pitching) hit
    a different code path (`s.decode('utf-8')`, done correctly) and were
    confirmed unaffected -- this is scoped to just Name on these two tables,
    not applied generically to every column/source.

    Reverses it by undoing exactly that transformation: decode the literal
    \\xHH escapes back into real bytes (unicode_escape, which treats each
    character as one raw byte -- a latin1 round-trip is byte-preserving),
    then decode those bytes as the real UTF-8 they always were. A name with
    no \\x escape (already correct -- e.g. if pybaseball fixes this
    upstream) is returned unchanged rather than risking a spurious re-encode.
    """
    if not isinstance(name, str) or "\\x" not in name:
        return name
    try:
        return name.encode("latin1").decode("unicode_escape").encode("latin1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return name


def _load_table(conn: psycopg.Connection, table: str, fn, season: int) -> int:
    df = call_with_retry(fn, season)
    if df.empty:
        return 0
    if "Name" in df.columns:
        df["Name"] = df["Name"].map(_repair_name_mojibake)
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


def _load_war(conn: psycopg.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table, fn in WAR_TABLES:
        try:
            df = call_with_retry(fn, return_all=False)
            counts[table] = load_dataframe(conn, table, df)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"bref: {table} failed ({exc}); skipping")
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
        for table, count in _load_war(conn).items():
            totals[table] = totals.get(table, 0) + count
        result["rows"] = sum(totals.values())
    return totals


def update() -> dict[str, int]:
    with get_connection() as conn, track_run(conn, SOURCE, "update") as result:
        totals = _load_season(conn, date.today().year)
        for table, count in _load_war(conn).items():
            totals[table] = totals.get(table, 0) + count
        result["rows"] = sum(totals.values())
    return totals


def health_check() -> list[Check]:
    return [
        check_table_has_rows("raw.bref_batting"),
        check_table_has_rows("raw.bref_pitching"),
        check_table_has_rows("raw.bref_war_batting"),
        check_table_has_rows("raw.bref_war_pitching"),
        check_last_run(SOURCE),
    ]
