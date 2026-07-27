"""Lands Baseball Savant's Statcast pitch-level tracking data into
raw.statcast_pitch, via pybaseball.statcast() — already a project dependency
(used for Lahman's network fallback, mlb_baseball/connectors/lahman.py).

Full history from 2008 (confirmed via direct testing: pybaseball.statcast()
returns real rows starting 2008 — the PITCHf/x era) through the present, per
explicit direction to ingest everything Statcast offers, period. Genuinely
two eras within this one table, not silently smoothed over — confirmed
directly, not assumed:
- **2008-2014 (PITCHf/x era)**: pitch trajectory/velocity/location
  populated, but Statcast-exclusive columns (launch_speed, release_spin_rate,
  and the ~90 derived/tracking columns after them) are null. Confirmed with a
  real sample: 2014-06-01 returned 4,103 rows, 0 with launch_speed or
  release_spin_rate populated. Real absence of data from that era (Trackman
  wasn't installed league-wide until 2015), not a parsing bug — don't
  "fix" this by backfilling or dropping pre-2015 rows.
- **2015-present (true Statcast/Trackman era)**: full 119-column fidelity —
  batted-ball tracking (exit velocity, launch angle, hit distance), spin
  rate/direction, derived sabermetric estimates (xBA, xwOBA, win-expectancy
  deltas), and bat-tracking (swing speed/angle, 2023+).

This is a strict superset of what MLB Stats API's own game feed offers for
pitch-level detail (~20 fields vs. 119, no batted-ball/derived/bat-tracking
data at all) — see mlb_baseball/connectors/mlb_api.py's module docstring and
docs/DECISIONS.md ADR-017 for the direct comparison that led to scoping all
pitch-level tracking here, and nowhere else in this pipeline.

Fetched in weekly date-range batches, not one day (or one game) at a time —
measured directly: a 7-day batch pulls ~25,000 rows in ~18 seconds (~2.6s/
day), vs. a single day alone taking ~53 seconds including per-request
overhead. A full season (~300 days spanning spring training through the
World Series) is roughly 13 minutes at this rate; the full 2008-present
history is estimated at several hours — long enough to matter, short enough
to run as a single background bootstrap.

Each weekly chunk is its own scoped-replace load (scope_column="_scope",
composite of season+chunk-start-date — same pattern as retrosheet_event/
retrosheet_box's `_scope`, see ADR-010) and commits independently, not
accumulated in memory for the whole season: a season's worth of pitches
(~700K+ rows x 119 columns) held entirely in memory before one big write
would be both a real memory cost and a resilience regression — a failure on
week 30 of 40 would otherwise lose every already-fetched week's data for
that season, not just the failed one.

bootstrap() loads full history one season at a time; update() reloads just
the current season (same season-scoped replace, so re-running is
idempotent). Unlike mlb_api.py, this connector isn't on a repeating cron
schedule (nothing here needs to be real-time — Statcast data for a game
isn't available until well after the game, and doesn't change), so
health_check() uses check_last_run, not check_recent_run.

Retry-with-backoff (net.call_with_retry) wraps every pybaseball.statcast()
call — proactively, not after a demonstrated failure this time (contrast
ADR-007/ADR-015): the sheer call volume here (2008-present in weekly chunks
is several hundred calls) makes hitting at least one transient failure
close to certain, the same reasoning that justified mlb_api.py's per-season/
per-game resilience layer.
"""

from datetime import date, timedelta

import pandas as pd
import psycopg
import pybaseball

from mlb_baseball.db import get_connection
from mlb_baseball.health import Check, check_last_run, check_table_has_rows
from mlb_baseball.ingest import track_run
from mlb_baseball.load import load_dataframe, season_already_loaded
from mlb_baseball.net import call_with_retry

SOURCE = "statcast"
FIRST_STATCAST_YEAR = 2008
TABLE = "raw.statcast_pitch"


def _season_date_ranges(season: int) -> list[tuple[date, date]]:
    """Weekly chunks covering the MLB season window (Feb-Nov, covers spring
    training through the World Series) — matches the batching confirmed fast
    in testing (~2.6s/day when requested in week-sized ranges)."""
    start = date(season, 2, 1)
    end = min(date(season, 12, 1), date.today())
    if start > end:
        return []
    ranges = []
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=6), end)
        ranges.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return ranges


def _fetch_range(start: date, end: date) -> pd.DataFrame:
    return call_with_retry(
        pybaseball.statcast, start_dt=start.isoformat(), end_dt=end.isoformat(), verbose=False
    )


def _load_week(conn: psycopg.Connection, season: int, start: date, end: date) -> int:
    df = _fetch_range(start, end)
    if df.empty:
        return 0
    scope = f"{season}_{start.isoformat()}"
    df["_season"] = str(season)
    df["_scope"] = scope
    return load_dataframe(conn, TABLE, df, scope_column="_scope", scope_value=scope)


def _load_season(conn: psycopg.Connection, season: int) -> int:
    total = 0
    for start, end in _season_date_ranges(season):
        try:
            total += _load_week(conn, season, start, end)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"statcast: {season} {start}-{end} failed ({exc}); skipping this week")
    return total


def bootstrap() -> dict[str, int]:
    current_year = date.today().year
    with get_connection() as conn, track_run(conn, SOURCE, "bootstrap") as result:
        total = 0
        for season in range(FIRST_STATCAST_YEAR, current_year + 1):
            # A past season's data is published and complete — it never
            # changes, so re-fetching it on every bootstrap re-run (each
            # season costs several minutes across dozens of weekly API
            # calls) is pure waste. Only the current season, still in
            # progress by definition, always gets re-fetched.
            if season < current_year and season_already_loaded(conn, TABLE, season):
                print(f"statcast: {season} already loaded, skipping")
                continue
            total += _load_season(conn, season)
        result["rows"] = total
    return {TABLE: total}


def update() -> dict[str, int]:
    with get_connection() as conn, track_run(conn, SOURCE, "update") as result:
        total = _load_season(conn, date.today().year)
        result["rows"] = total
    return {TABLE: total}


def health_check() -> list[Check]:
    return [
        check_table_has_rows(TABLE),
        check_last_run(SOURCE),
    ]
