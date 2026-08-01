"""Prior-season (lagged one full season) team defensive value via
Statcast Outs Above Average (ADR-040, docs/RESEARCH.md item 8). UZR/DRS
(FanGraphs' own defensive metrics) depend on proprietary positioning
data with no free path to replicate -- a permanent wall under this
project's $0-budget rule, confirmed directly (`docs/DATA_SOURCES.md`:
FanGraphs' own site returns HTTP 403 for every scrape attempt, not an
occasional failure). `raw.statcast_oaa.fielding_runs_prevented` (Statcast's
own runs-translated OAA, already ingested 2016-2026 via
`statcast_leaderboard.py`) is the real, free substitute this project
already has sitting unused.

Lagged, not current-season, for the same reason as war.py: OAA is a
season aggregate Baseball Savant only ever publishes cumulative
year-to-date-and-final numbers for, not a per-game log this project could
derive a genuine within-season rolling window from the way starter.py/
offense.py do -- so a team's *current*-season OAA used mid-season would
leak every game played after the one being predicted, the same trap
ADR-032 named for WAR.

Grain and join: raw.statcast_oaa is per PLAYER per SEASON per POSITION
(confirmed directly -- `_scope` values like "2016_3", "2016_4" are
year_position, not a duplicate-row bug; a player who played multiple
positions in a season has one row per position, each contributing
separately to their season defensive total, so summing across all of a
player's rows for a season is correct, not double-counting). `player_id`
is the player's MLBAM id, matching `core.player.mlbam_id` directly --
no crosswalk needed there, unlike war.py's bref/Retrosheet team-code
problem. Team identity is the harder part: `display_team_name` is
Savant's own short nickname text (e.g. "D-backs", "Rays", "Guardians"),
confirmed directly to diverge from `core.team.nickname` in exactly three
cases -- two abbreviation-style shortenings (D-backs/Diamondbacks) and
one franchise rename core.team never split into a separate row for
(Guardians/Indians share one team row spanning 1901-9999, the same
"one row per relocation, not per rename" pattern the Oakland Athletics'
three separate first_year/last_year rows already establish elsewhere in
this schema). A small three-entry CASE remap handles it; every other
name matches `core.team.nickname` verbatim. Rows with `display_team_name
= '---'` (confirmed present -- players with no clear primary team for
that season) are excluded rather than guessed.
"""

import psycopg

from mlb_baseball.health import Check, check_table_has_rows

_COMPUTE_SQL = """
WITH team_season_oaa AS (
    SELECT
        CASE o.display_team_name
            WHEN 'D-backs' THEN 'Diamondbacks'
            WHEN 'Rays' THEN 'Devil Rays'
            WHEN 'Guardians' THEN 'Indians'
            ELSE o.display_team_name
        END AS nickname,
        o.year::integer AS season,
        sum(o.fielding_runs_prevented::numeric) AS total_oaa
    FROM raw.statcast_oaa o
    WHERE o.display_team_name != '---'
    GROUP BY 1, 2
),
team_oaa_resolved AS (
    SELECT t.id AS team_id, tso.season, tso.total_oaa
    FROM team_season_oaa tso
    JOIN core.team t
        ON t.nickname = tso.nickname
        AND tso.season BETWEEN t.first_year AND t.last_year
)
UPDATE gold.game_feature f
SET
    home_oaa_prior = ho.total_oaa,
    away_oaa_prior = ao.total_oaa
FROM core.game g
LEFT JOIN team_oaa_resolved ho ON ho.team_id = g.home_team_id AND ho.season = g.season - 1
LEFT JOIN team_oaa_resolved ao ON ao.team_id = g.away_team_id AND ao.season = g.season - 1
WHERE f.game_id = g.id
"""


def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_oaa')")
        (exists,) = cur.fetchone()
        if not exists:
            return 0
        cur.execute(_COMPUTE_SQL)
        return cur.rowcount


def health_check() -> list[Check]:
    return [check_table_has_rows("gold.game_feature")]
