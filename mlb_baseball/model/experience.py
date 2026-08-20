"""Starter career experience entering a game (ADR-085, admission queue
PLN-04's "prior MLB PA/IP" half, docs/FEATURE_ADMISSION_QUEUE.md). Career
batters-faced and innings-pitched, counted the same way
team_starter_retrosheet_update.sql's own pitcher_game_stats CTE already
counts a season total (starter.py, ADR-034) -- the only difference is the
rolling window has no season partition, spanning a pitcher's whole
Retrosheet-covered career instead of resetting each season.

This is the deferred half of PLN-04 that ADR-084's age.py (a sibling,
independently-branched PR from the same session) explicitly left for
later: age.py only covers "age on game date" from already-populated
gold.game_feature/core.player columns; this module is the "prior MLB
PA/IP" half, which genuinely needs new raw-derived career-cumulative
window SQL rather than pure algebra over existing columns. A real, weak
service-time/experience signal, distinct from age itself (a rookie and a
15-year veteran can be the same age; a late debut and an early debut
starter can have wildly different career innings at the same age) --
whether it actually helps gbm-v1's held-out log-loss is a separate, later
retrain question, not assumed here.

Deliberately independent of starter.py's own module rather than adding a
career window to team_starter_retrosheet_update.sql directly -- that file
already computes a season-partitioned window for K%/BB%/HR%/FIP, and
folding an unrelated, unbounded career window into the same query would
make it harder to reason about and test in isolation. Duplicates
pitcher_game_stats' shape rather than importing it, since SQL files in
this codebase are standalone (mlb_baseball/sql/read_sql), not composed --
same posture as every other *_update.sql file here.

Career totals intentionally include relief appearances, not just starts
(PR review, Kilo, confirmed intentional rather than an oversight):
pitcher_game_stats sums every appearance a pitcher recorded, regardless
of that game's own start/relief role, so a swingman's career BF/IP
reflects his whole MLB career. "Prior MLB PA/IP" in the admission
queue's own words is a general experience/service-time proxy, not
specifically "prior starts' worth of PA/IP" -- relief innings are real
MLB pitching experience too, and excluding them would understate a
swingman's actual career experience.
"""

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check
from mlb_baseball.sql import read_sql

# Plausible-range bounds for health_check() -- checked against the real,
# all-time MLB career records (PR review, Kilo, then verified directly
# rather than assumed correct): Cy Young holds both records, 29,565
# career batters faced and 7,356 career innings pitched (a 22-year,
# dead-ball-era career never surpassed since). Bounds sit with real
# headroom above those, not a tight guess -- an earlier draft used
# 20,000/6,000, which would have flagged Cy Young's own real numbers as
# implausible had his full career ever loaded into this system.
BF_MIN, BF_MAX = 0, 32000
IP_MIN, IP_MAX = 0, 8000


def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        # Two-table dependency, two-table gate (same shape as
        # starter.py::compute, issue #9 item 2): retrosheet_event and
        # retrosheet_gameinfo are landed by two different connectors.
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (event_exists,) = fetch_one(cur)
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        (gameinfo_exists,) = fetch_one(cur)
        if not event_exists or not gameinfo_exists:
            return 0
        cur.execute(read_sql("starter_experience_update.sql"))
        return cur.rowcount


def health_check() -> list[Check]:
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT "
            "count(*) FILTER ("
            "  WHERE home_starter_career_bf IS NOT NULL "
            "  AND (home_starter_career_bf < %(bf_min)s OR home_starter_career_bf > %(bf_max)s)"
            "), "
            "count(*) FILTER ("
            "  WHERE home_starter_career_ip IS NOT NULL "
            "  AND (home_starter_career_ip < %(ip_min)s OR home_starter_career_ip > %(ip_max)s)"
            "), "
            "count(*) FILTER ("
            "  WHERE away_starter_career_bf IS NOT NULL "
            "  AND (away_starter_career_bf < %(bf_min)s OR away_starter_career_bf > %(bf_max)s)"
            "), "
            "count(*) FILTER ("
            "  WHERE away_starter_career_ip IS NOT NULL "
            "  AND (away_starter_career_ip < %(ip_min)s OR away_starter_career_ip > %(ip_max)s)"
            ") "
            "FROM gold.game_feature",
            {"bf_min": BF_MIN, "bf_max": BF_MAX, "ip_min": IP_MIN, "ip_max": IP_MAX},
        )
        bad_home_bf, bad_home_ip, bad_away_bf, bad_away_ip = fetch_one(cur)

    def _check(name: str, bad: int, bounds: str) -> Check:
        if bad:
            return Check(name, False, f"{bad} rows outside {bounds}")
        return Check(name, True, f"all computed values within {bounds}")

    bf_bounds = f"{BF_MIN}-{BF_MAX}"
    ip_bounds = f"{IP_MIN}-{IP_MAX}"

    return [
        _check("home_starter_career_bf plausible range", bad_home_bf, bf_bounds),
        _check("home_starter_career_ip plausible range", bad_home_ip, ip_bounds),
        _check("away_starter_career_bf plausible range", bad_away_bf, bf_bounds),
        _check("away_starter_career_ip plausible range", bad_away_ip, ip_bounds),
    ]
