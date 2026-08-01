"""Prior-season (lagged one full season) team catcher-framing value via
Statcast (ADR-045, docs/RESEARCH.md). A real, distinct signal from
everything else built so far: starter.py/bullpen.py's FIP measures
results a pitcher directly controls (DIPS theory), while framing
measures a catcher's effect on called-strike rate -- a separate
mechanism entirely, not something FIP already prices in.

Lagged, not current-season, for the same reason as war.py/oaa.py:
raw.statcast_framing is a season aggregate, not a per-game log -- a
team's *current*-season framing value used mid-season would leak every
game played after the one being predicted.

Team identity is resolved through core.player_war, not a direct team
column (raw.statcast_framing has none -- checked directly, same shape
as the already-rejected xwOBA/exitvelo tables, see docs/RESEARCH.md).
Reuses war.py's own _BREF_TO_RETRO crosswalk (core.player_war.team_code
is bref's own abbreviation, same as war.py's problem) rather than
duplicating it -- a second, independently-maintained copy of the same
30-team mapping would only risk silently drifting from the original.

Real coverage gap found and understood before building, not glossed
over: only ~52% of raw.statcast_framing rows resolve to a team this
way (confirmed directly against 2024 data) -- the unresolved half are
consistently rookies/prospects with too little playing time for
core.player_war's own minimum-PA threshold to include them (e.g. 2024's
Samuel Basallo, Dalton Rushing, Carter Jensen, Drake Baldwin -- verified
by name, not a join bug). This mirrors the same "the gap is real,
understood, and comes from the reference source's own known limit, not
this module's logic" pattern as starter.py's ~1.7% Retrosheet gap.
"""

import psycopg

from mlb_baseball.db import fetch_one
from mlb_baseball.health import Check, check_table_has_rows
from mlb_baseball.model.war import _BREF_TO_RETRO

_COMPUTE_SQL = """
WITH catcher_team AS (
    SELECT p.id AS player_id, f._season::integer AS season,
        f.rv_tot::numeric AS rv_tot, pw.team_code
    FROM raw.statcast_framing f
    JOIN core.player p ON p.mlbam_id = f.id
    JOIN core.player_war pw
        ON pw.player_id = p.id AND pw.season = f._season::integer AND pw.is_pitcher = false
),
bref_map (bref_code, retro_code) AS (VALUES {values_clause}),
team_season_framing AS (
    SELECT t.id AS team_id, ct.season, sum(ct.rv_tot) AS total_framing
    FROM catcher_team ct
    JOIN bref_map bm ON bm.bref_code = ct.team_code
    JOIN core.team t
        ON t.retro_team_id = bm.retro_code
        AND ct.season BETWEEN t.first_year AND t.last_year
    GROUP BY t.id, ct.season
)
UPDATE gold.game_feature f
SET
    home_framing_prior = hf.total_framing,
    away_framing_prior = af.total_framing
FROM core.game g
LEFT JOIN team_season_framing hf ON hf.team_id = g.home_team_id AND hf.season = g.season - 1
LEFT JOIN team_season_framing af ON af.team_id = g.away_team_id AND af.season = g.season - 1
WHERE f.game_id = g.id
"""


def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_framing')")
        (exists,) = fetch_one(cur)
        if not exists:
            return 0
        values_clause = ", ".join(
            f"('{bref}', '{retro}')" for bref, retro in _BREF_TO_RETRO.items()
        )
        cur.execute(_COMPUTE_SQL.format(values_clause=values_clause))
        return cur.rowcount


def health_check() -> list[Check]:
    return [check_table_has_rows("gold.game_feature")]
