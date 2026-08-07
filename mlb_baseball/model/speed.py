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
from mlb_baseball.sql import read_sql


def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_sprint_speed')")
        (exists,) = fetch_one(cur)
        if not exists:
            return 0
        cur.execute(read_sql("team_speed_update.sql"))
        return cur.rowcount


def health_check() -> list[Check]:
    return [check_table_has_rows("gold.game_feature")]
