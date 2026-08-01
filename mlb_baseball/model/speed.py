"""Prior-season (lagged one full season) team baserunning speed via
Statcast Sprint Speed (ADR-041, docs/RESEARCH.md). Not covered by any
other feature in this project -- WAR/OAA/bullpen/starter/wOBA all touch
hitting, pitching, or fielding value, but nothing here captures raw
team speed, which sabermetric research treats as a real, separable
input (baserunning value, infield-hit/double-play-avoidance rates all
trace back to it) rather than something wOBA/wRC+ already price in.

Lagged, not current-season, for the same reason as war.py/oaa.py:
`raw.statcast_sprint_speed` is a season aggregate Baseball Savant only
publishes a cumulative number for, not a per-game log -- a team's
*current*-season speed used mid-season would leak every game played
after the one being predicted.

Team identity here is the easy case, unlike war.py's bref/Retrosheet
crosswalk or oaa.py's three-name remap: `raw.statcast_sprint_speed.
team_id` is MLB's own numeric team id, confirmed directly to match
`core.team.mlb_team_id` verbatim across all 30 current teams -- no
crosswalk needed at all.

Weighted by `competitive_runs` (the number of qualifying competitive
runs Statcast measured for that player that season), not a plain
average across a team's roster -- a bench player's 5-run sample
shouldn't count the same as an everyday player's 150-run sample when
representing the team's actual on-field speed.
"""

import psycopg

from mlb_baseball.db import fetch_one
from mlb_baseball.health import Check, check_table_has_rows

_COMPUTE_SQL = """
WITH team_season_speed AS (
    SELECT
        s.team_id::integer AS mlb_team_id,
        s._season::integer AS season,
        sum(s.sprint_speed::numeric * s.competitive_runs::numeric)
            / sum(s.competitive_runs::numeric) AS weighted_speed
    FROM raw.statcast_sprint_speed s
    WHERE s.competitive_runs::numeric > 0
    GROUP BY 1, 2
),
team_speed_resolved AS (
    SELECT t.id AS team_id, tss.season, tss.weighted_speed
    FROM team_season_speed tss
    JOIN core.team t
        ON t.mlb_team_id = tss.mlb_team_id
        AND tss.season BETWEEN t.first_year AND t.last_year
)
UPDATE gold.game_feature f
SET
    home_speed_prior = hs.weighted_speed,
    away_speed_prior = aws.weighted_speed
FROM core.game g
LEFT JOIN team_speed_resolved hs ON hs.team_id = g.home_team_id AND hs.season = g.season - 1
LEFT JOIN team_speed_resolved aws ON aws.team_id = g.away_team_id AND aws.season = g.season - 1
WHERE f.game_id = g.id
"""


def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_sprint_speed')")
        (exists,) = fetch_one(cur)
        if not exists:
            return 0
        cur.execute(_COMPUTE_SQL)
        return cur.rowcount


def health_check() -> list[Check]:
    return [check_table_has_rows("gold.game_feature")]
