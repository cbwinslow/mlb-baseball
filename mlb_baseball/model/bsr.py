"""Team prior stolen-base run value, wSB (ADR-081, admission queue BSR-01,
docs/FEATURE_ADMISSION_QUEUE.md). Same point-in-time-safe, entering-value
shape as team_rate.py's OBP/SLG family: every value is computed only from
games strictly before the one it's attached to.

Formula (Tom Tango's linear-weights methodology, decades old and publicly
documented -- see the FanGraphs library page cited in the admission
queue's BSR-01 row):

    wSB = SB*runSB + CS*runCS - lgwSB*(1B+BB+HBP-IBB)
    lgwSB = (lgSB*runSB + lgCS*runCS) / (lg1B+lgBB+lgHBP-lgIBB)

RUN_SB/RUN_CS below are the widely-cited fixed Tango constants (runSB
about +0.2, runCS about -0.4 to -0.5) rather than a per-season refit --
FanGraphs' own year-by-year linear weights aren't public in closed form,
and the admission queue's own research already settled on these as the
cited, defensible constants. "1B+BB+HBP-IBB" is computed directly as
"1B+UBB+HBP" in the SQL (BB-IBB cancels the IBB term exactly, since
BB = UBB+IBB) -- see team_bsr_retrosheet_update.sql's own docstring for
the full derivation and the real-data verification that SB/CS counting
must NOT be gated on bat_event_fl='T' the way 1B/BB/HBP counting is.

MIN_ATTEMPTS is a chosen, documented sample-size floor (not derived from
citation), scaled for this module's entering-value context the same way
team_rate.py's own MIN_PA/MIN_AB are: stolen-base attempts accumulate far
slower per team-game than plate appearances do, so a PA-scaled minimum
would leave most of a season NULL.
"""

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check
from mlb_baseball.sql import read_sql

RUN_SB = 0.2
RUN_CS = -0.42

MIN_ATTEMPTS = 5

# Plausible-range bounds for health_check() -- see team_bsr_health_check.sql's
# own docstring for why these are deliberately generous.
WSB_MIN, WSB_MAX = -15, 15


def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        # Two-table dependency, two-table gate (same shape as
        # team_rate.py::compute, issue #9 item 2): retrosheet_event and
        # retrosheet_gameinfo are landed by two different connectors.
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (event_exists,) = fetch_one(cur)
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        (gameinfo_exists,) = fetch_one(cur)
        if not event_exists or not gameinfo_exists:
            return 0
        cur.execute(
            read_sql("team_bsr_retrosheet_update.sql"),
            {"run_sb": RUN_SB, "run_cs": RUN_CS, "min_attempts": MIN_ATTEMPTS},
        )
        return cur.rowcount


def health_check() -> list[Check]:
    with get_connection() as conn, conn.cursor() as cur:
        # REPEATABLE READ so the range query and the coverage query below
        # see one consistent snapshot of gold.game_feature -- same
        # reasoning as team_rate.py::health_check (PR #54 review).
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        cur.execute(
            read_sql("team_bsr_health_check.sql"),
            {"wsb_min": WSB_MIN, "wsb_max": WSB_MAX, "min_attempts": MIN_ATTEMPTS},
        )
        (
            bad_wsb,
            bad_gate,
            bad_sb_negative,
            bad_cs_negative,
            bad_away_wsb,
            bad_away_gate,
            bad_away_sb_negative,
            bad_away_cs_negative,
        ) = fetch_one(cur)

        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (event_exists,) = fetch_one(cur)
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        (gameinfo_exists,) = fetch_one(cur)
        if event_exists and gameinfo_exists:
            cur.execute(read_sql("team_bsr_coverage_health_check.sql"))
            bad_home_sb_coverage, bad_away_sb_coverage = fetch_one(cur)
        else:
            bad_home_sb_coverage = bad_away_sb_coverage = 0

    def _check(name: str, bad: int, bounds: str) -> Check:
        if bad:
            return Check(name, False, f"{bad} rows outside {bounds}")
        return Check(name, True, f"all computed values within {bounds}")

    def _coverage_check(name: str, bad: int) -> Check:
        if bad:
            return Check(name, False, f"{bad} eligible rows have no computed value")
        return Check(name, True, "every eligible row has a computed value")

    wsb_bounds = f"{WSB_MIN}-{WSB_MAX}"

    return [
        _check("home_wsb plausible range", bad_wsb, wsb_bounds),
        _check("home_wsb min-sample gate holds", bad_gate, f"sb+cs >= {MIN_ATTEMPTS}"),
        _check("home_sb non-negative", bad_sb_negative, "0+"),
        _check("home_cs non-negative", bad_cs_negative, "0+"),
        _check("away_wsb plausible range", bad_away_wsb, wsb_bounds),
        _check("away_wsb min-sample gate holds", bad_away_gate, f"sb+cs >= {MIN_ATTEMPTS}"),
        _check("away_sb non-negative", bad_away_sb_negative, "0+"),
        _check("away_cs non-negative", bad_away_cs_negative, "0+"),
        _coverage_check("home_sb coverage", bad_home_sb_coverage),
        _coverage_check("away_sb coverage", bad_away_sb_coverage),
    ]
