"""Starter age on game date (ADR-087, admission queue PLN-04,
docs/archive/FEATURE_ADMISSION_QUEUE.md). Pure derived value over two already-
populated pieces -- gold.game_feature's own home_starter_id/away_starter_id
(resolved by starter.py) and core.player.birth_date -- no new raw-event
dependency, same "derive from a prior step's own output" shape as
diff.py/trend.py.

Deliberately narrower than the admission queue's own PLN-04 row, which
also calls for "prior MLB PA/IP" (a career-experience/service-time proxy)
alongside age. That half needs a genuinely new career-cumulative rolling
window over raw.retrosheet_event (UNBOUNDED PRECEDING across a pitcher's
whole career, not just within-season, unlike every existing rolling
window in this codebase) -- real, separate follow-up work, not bundled
into this narrowly-scoped change. Team-level weighted age is documented
elsewhere (docs/RESEARCH.md, FanGraphs r^2=.12 -- a real but weak signal)
as only weakly predictive at team grain; this module deliberately targets
starter-specific age instead, where the research signal (aging curves
affecting a single pitcher's current performance) is more directly
applicable than a team-wide average would be.

compute() must run after starter.compute() has resolved home_starter_id/
away_starter_id for the day's games -- enrich_feature_stage() enforces
this via dispatch order, not a runtime check (same posture as diff.py's
own dependency on offense.compute_wrc_plus()).
"""

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check
from mlb_baseball.sql import read_sql

# Plausible-range bounds for health_check() -- youngest MLB debut on
# record is in the teens (e.g. Joe Nuxhall at 15); no starter has ever
# started past 59 (Satchel Paige) -- generous bounds around both, not a
# tight age-curve assumption.
AGE_MIN, AGE_MAX = 15, 60


def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute(read_sql("starter_age_update.sql"))
        return cur.rowcount


def health_check() -> list[Check]:
    """Plausible-range check, not algebraic parity -- unlike diff.py/
    trend.py, this doesn't re-derive from a stored formula parameter
    (birth_date arithmetic doesn't round-trip cleanly through IS DISTINCT
    FROM at numeric precision), so a bounds check is the right shape,
    matching team_rate.py's own posture for its rate-stat columns."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT "
            "count(*) FILTER ("
            "  WHERE home_starter_age IS NOT NULL "
            "  AND (home_starter_age < %(age_min)s OR home_starter_age > %(age_max)s)"
            "), "
            "count(*) FILTER ("
            "  WHERE away_starter_age IS NOT NULL "
            "  AND (away_starter_age < %(age_min)s OR away_starter_age > %(age_max)s)"
            ") "
            "FROM gold.game_feature",
            {"age_min": AGE_MIN, "age_max": AGE_MAX},
        )
        bad_home, bad_away = fetch_one(cur)

    def _check(name: str, bad: int) -> Check:
        bounds = f"{AGE_MIN}-{AGE_MAX}"
        if bad:
            return Check(name, False, f"{bad} rows outside {bounds}")
        return Check(name, True, f"all computed values within {bounds}")

    return [
        _check("home_starter_age plausible range", bad_home),
        _check("away_starter_age plausible range", bad_away),
    ]
