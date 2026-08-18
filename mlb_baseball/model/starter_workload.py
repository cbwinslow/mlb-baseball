"""Starter rest and workload (PIT-03, docs/FEATURE_ADMISSION_QUEUE.md).

Computes starting-pitcher rest days (calendar days since the starting
pitcher's immediately preceding start) and trailing 7-day workload (sum of
all outs pitched in any role across the preceding 7 calendar days),
strictly point-in-time and without leakage.

Reused patterns and design choices:
1. Day-collapse RANGE frame (ADR-042): trailing workload is computed by
   collapsing outs to one row per (pitcher, calendar day) first, then applying
   a window RANGE frame (RANGE BETWEEN INTERVAL '7 days' PRECEDING
   AND INTERVAL '1 day' PRECEDING). As documented in ADR-042 for bullpen
   fatigue, collapsing to day grain first eliminates peer-row ambiguity on
   doubleheaders while keeping the computation linear (O(N)) across historical
   data.
2. Units: outs, not pitches. Ingested raw.retrosheet_event records event_outs_ct
   per play but does not include pitch-by-pitch counts in this project's ingested
   source. Outs provides a direct, verifiable workload proxy without ungrounded
   imputation, matching bullpen fatigue's own precedent.
3. Fixed window: implements a single trailing window
   (WORKLOAD_WINDOW_DAYS = 7, mirroring bullpen fatigue's FATIGUE_WINDOW_DAYS = 3).
   7 days captures a starter's prior regular turn in a 5-day rotation plus any
   recent relief outings.
4. Pitcher-level rest calculation: rest days is computed specifically between
   starts (restricted to resp_pit_start_fl = 'T'), using LAG() partitioned by
   pitcher_retro_id ordered by game_date, game_id. A pitcher's very first tracked
   start correctly leaves both rest_days and outs_7d NULL.

Scope: Retrosheet-historical path (compute(), covering 1910-2025),
live 2026 play-by-play (compute_live()), and forward-looking probable
starter path (compute_probable()).
"""

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check
from mlb_baseball.sql import read_sql

WORKLOAD_WINDOW_DAYS = 7


def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        # Two-table dependency, two-table gate (issue #9 item 2): the SQL
        # below also joins raw.retrosheet_gameinfo -- see team_rate.py's
        # compute() for the full explanation (two different connectors).
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (event_exists,) = fetch_one(cur)
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        (gameinfo_exists,) = fetch_one(cur)
        if not event_exists or not gameinfo_exists:
            return 0
        cur.execute(read_sql("starter_workload_retrosheet_update.sql"))
        return cur.rowcount


def compute_live(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_playbyplay')")
        (exists,) = fetch_one(cur)
        if not exists:
            return 0
        cur.execute(read_sql("starter_workload_live_update.sql"))
        return cur.rowcount


def compute_probable(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_probable')")
        (probable_exists,) = fetch_one(cur)
        cur.execute("SELECT to_regclass('raw.mlb_playbyplay')")
        (playbyplay_exists,) = fetch_one(cur)
        if not probable_exists or not playbyplay_exists:
            return 0
        cur.execute(
            read_sql("starter_workload_probable_update.sql"),
            {"workload_days": WORKLOAD_WINDOW_DAYS},
        )
        return cur.rowcount


def health_check() -> list[Check]:
    """Internal consistency and coverage check: rest days and workload outs
    have no external published season aggregate to reconcile against (unlike
    starter.py's rate stats vs raw.bref_pitching). Instead, this verifies:
    1. Bounds sanity: zero negative rest days or negative workload outs
       (already checked on both home and away sides).
    2. Coverage, checked on both home and away sides (issue #9 item 3: the
       two resolve through the same logic but two different join legs, so
       an away-only join bug is a real, if unlikely, failure mode a
       home-only check can't surface): for completed regular-season games
       beyond the season's opening month (May onwards) where a starting
       pitcher was resolved, the vast majority (>=90%, see _coverage_check's
       own `coverage < 0.90` threshold) have a populated rest_days value
       (only mid-season debuts or newly acquired pitchers with no prior
       tracked starts lack a prior start).
    """
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('gold.game_feature')")
        (exists,) = fetch_one(cur)
        if not exists:
            return [
                Check(
                    "starter workload: gold.game_feature presence",
                    False,
                    "gold.game_feature does not exist",
                )
            ]
        cur.execute(read_sql("starter_workload_health_check.sql"))
        (
            neg_rest,
            neg_outs,
            unpop_may_rest,
            total_may_starts,
            unpop_may_away_rest,
            total_may_away_starts,
        ) = fetch_one(cur)

    checks = []
    if neg_rest > 0:
        checks.append(
            Check(
                "starter workload: non-negative rest days",
                False,
                f"{neg_rest} rows with negative rest days",
            )
        )
    else:
        checks.append(Check("starter workload: non-negative rest days", True, "all rest days >= 0"))

    if neg_outs > 0:
        checks.append(
            Check(
                "starter workload: non-negative workload outs",
                False,
                f"{neg_outs} rows with negative workload outs",
            )
        )
    else:
        checks.append(
            Check("starter workload: non-negative workload outs", True, "all workload outs >= 0")
        )

    checks.append(_coverage_check("home", unpop_may_rest, total_may_starts))
    checks.append(_coverage_check("away", unpop_may_away_rest, total_may_away_starts))

    return checks


def _coverage_check(side: str, unpopulated: int, total: int) -> Check:
    name = f"starter workload: May+ rest days coverage for resolved {side} starters"
    if total <= 0:
        return Check(name, True, "no completed May+ starts to evaluate")
    coverage = 1.0 - (unpopulated / total)
    populated = total - unpopulated
    if coverage < 0.90:
        return Check(
            name,
            False,
            f"{coverage:.1%} coverage ({populated}/{total} populated, {unpopulated} missing)",
        )
    return Check(name, True, f"{coverage:.1%} coverage ({populated}/{total} populated)")
