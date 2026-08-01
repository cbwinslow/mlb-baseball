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

TRAILING_SEASONS = 3

_COMPUTE_SQL = """
WITH home_splits AS (
    SELECT home_team_id AS team_id, season, venue_id,
        count(*) AS games, sum(home_score + away_score) AS runs
    FROM core.game
    WHERE game_type = 'regular' AND home_score IS NOT NULL
        AND away_score IS NOT NULL AND venue_id IS NOT NULL
    GROUP BY home_team_id, season, venue_id
),
road_splits AS (
    SELECT away_team_id AS team_id, season,
        count(*) AS games, sum(home_score + away_score) AS runs
    FROM core.game
    WHERE game_type = 'regular' AND home_score IS NOT NULL AND away_score IS NOT NULL
    GROUP BY away_team_id, season
),
team_season_pf AS (
    SELECT h.team_id, h.season, h.venue_id,
        (h.runs::numeric / NULLIF(h.games, 0)) AS home_rate,
        (r.runs::numeric / NULLIF(r.games, 0)) AS road_rate
    FROM home_splits h
    JOIN road_splits r ON r.team_id = h.team_id AND r.season = h.season
),
venue_seasons_needed AS (
    SELECT DISTINCT venue_id, season FROM gold.game_feature WHERE venue_id IS NOT NULL
),
venue_trailing AS (
    SELECT n.venue_id, n.season AS target_season,
        avg(100.0 * b.home_rate / NULLIF(b.road_rate, 0)) AS park_factor
    FROM venue_seasons_needed n
    JOIN team_season_pf b ON b.venue_id = n.venue_id
        AND b.season BETWEEN n.season - %(trailing_seasons)s AND n.season - 1
    GROUP BY n.venue_id, n.season
)
UPDATE gold.game_feature f
SET park_factor = v.park_factor
FROM venue_trailing v
WHERE f.venue_id = v.venue_id AND f.season = v.target_season
"""


def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute(_COMPUTE_SQL, {"trailing_seasons": TRAILING_SEASONS})
        return cur.rowcount


def health_check() -> list[Check]:
    """Real MLB park factors have never been observed outside roughly
    80-130 (Coors Field, the most extreme modern hitter's park, sits
    around 110-120) -- checking gold.game_feature's own rows for a
    duplicate-table-has-rows check would be redundant with features.py's
    own check, so this instead sanity-bounds the actual computed values,
    which would catch a real bug (e.g. an inverted home/road ratio,
    which would produce values near 0 or in the thousands) that a mere
    presence check never would."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM gold.game_feature "
            "WHERE park_factor IS NOT NULL AND (park_factor < 50 OR park_factor > 200)"
        )
        (bad,) = fetch_one(cur)
    if bad:
        return [Check("park_factor plausible range", False, f"{bad} rows outside 50-200")]
    return [Check("park_factor plausible range", True, "all computed values within 50-200")]
