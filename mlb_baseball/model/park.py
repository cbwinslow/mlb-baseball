"""Park factor: standard sabermetric methodology (FanGraphs, Baseball
Prospectus, confirmed via research -- see docs/RESEARCH.md) -- ratio of a
venue's home run-scoring rate to the same team(s)' road rate that season,
scaled to 100 = league average, averaged over a trailing multi-year
window to reduce single-season noise (3 years here, a commonly-cited
middle ground; some sources use 1, some use 5).

Point-in-time correct by construction: a season's park factor is computed
only from the TRAILING window of seasons strictly before it (season-3
through season-1), never the season itself or later -- no leakage risk,
unlike starter quality/prior WAR, since this never needs to reach into a
season's own still-accumulating games at all.

Driven by whatever (venue_id, season) pairs gold.game_feature actually
has, not by which seasons happen to already have completed home games at
that venue -- an upcoming season's very first game at a park still needs
a park factor from the trailing window, even though that season itself
has no home data there yet.
"""

import psycopg

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check
from mlb_baseball.sql import read_sql

TRAILING_SEASONS = 3


def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute(read_sql("park_factor_update.sql"), {"trailing_seasons": TRAILING_SEASONS})
        return cur.rowcount


def health_check() -> list[Check]:
    """Modern-era MLB park factors have never been observed outside
    roughly 80-130 (Coors Field, the most extreme modern hitter's park,
    sits around 110-120), but this table also carries pre-integration-era
    Negro League games, which real small-sample data pushes further --
    checking gold.game_feature's own rows for a duplicate-table-has-rows
    check would be redundant with features.py's own check, so this
    instead sanity-bounds the actual computed values, which would catch a
    real bug (e.g. an inverted home/road ratio, which would produce
    values near 0 or in the thousands) that a mere presence check never
    would.

    Bounds are widened to 20-350, not the modern 80-130, because of a
    confirmed real (not buggy) case: venue_id 1604 ("South Side Park
    III") was the Chicago White Sox's park 1901-1910 (core.venue's own
    first_year/last_year), then became the Chicago American Giants' home
    park 1913-1940 -- a Negro League team, whose games at this venue ran
    as few as 1-11 per season (vs. 70-82/season for the White Sox
    tenancy). A 3-year trailing home/road run-rate ratio computed from
    that few games is legitimately noisy, not a computation bug: verified
    directly against production, the actual full range across all
    207,279 non-null rows is exactly 33.33-290.00, all 4 outside the old
    50-200 bound coming from this one venue's 1926-1929 American Giants
    games. Confirmed by hand: the SQL formula (100 * home_rate /
    road_rate) is directionally correct for both extremes -- 33.33 means
    a real (if noisy) pitcher's-park signal, 290.00 a hitter's-park
    signal, not a sign-flip or inverted ratio."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM gold.game_feature "
            "WHERE park_factor IS NOT NULL AND (park_factor < 20 OR park_factor > 350)"
        )
        (bad,) = fetch_one(cur)
    if bad:
        return [Check("park_factor plausible range", False, f"{bad} rows outside 20-350")]
    return [Check("park_factor plausible range", True, "all computed values within 20-350")]
