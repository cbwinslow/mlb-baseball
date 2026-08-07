"""Prior-season (lagged one full season) team WAR (ADR-038) -- fills the
already-reserved home_war_prior/away_war_prior columns (ADR-032), unbuilt
until now. Lagged, not current-season: core.player_war is a season
aggregate (Baseball-Reference only ever publishes it once per season),
so a team's *current*-season WAR used mid-season would leak every game
played after the one being predicted -- the exact trap ADR-032 already
named this column for. Prior season carries zero leakage risk by
construction: it's entirely in the past relative to any game in the
current season.

core.player_war.team_code uses Baseball-Reference's own team
abbreviations (e.g. NYY, CHC, SFG), which genuinely differ from
Retrosheet's (NYA, CHN, SFN) that core.team.retro_team_id uses -- a real,
separate team-identity crosswalk problem, confirmed directly by comparing
the two code sets, not assumed to line up. _BREF_TO_RETRO covers the
current 30 teams (where this feature has the most real value -- recent
seasons, not deep historical backtesting); older teams whose bref/retro
codes diverge differently across relocations/renames aren't covered and
correctly get NULL rather than a guessed number.
"""

import psycopg

from mlb_baseball.health import Check, check_table_has_rows
from mlb_baseball.sql import read_sql

# bref team_code -> Retrosheet retro_team_id, for the current 30 teams --
# see module docstring for why this is a fixed, current-era mapping, not
# a full historical crosswalk.
_BREF_TO_RETRO = {
    "ARI": "ARI",
    "ATL": "ATL",
    "BAL": "BAL",
    "BOS": "BOS",
    "CHC": "CHN",
    "CHW": "CHA",
    "CIN": "CIN",
    "CLE": "CLE",
    "COL": "COL",
    "DET": "DET",
    "HOU": "HOU",
    "KCR": "KCA",
    "LAA": "ANA",
    "LAD": "LAN",
    "MIA": "MIA",
    "MIL": "MIL",
    "MIN": "MIN",
    "NYM": "NYN",
    "NYY": "NYA",
    "OAK": "OAK",
    "PHI": "PHI",
    "PIT": "PIT",
    "SDP": "SDN",
    "SEA": "SEA",
    "SFG": "SFN",
    "STL": "SLN",
    "TBR": "TBA",
    "TEX": "TEX",
    "TOR": "TOR",
    "WSN": "WAS",
}


def compute(conn: psycopg.Connection) -> int:
    # No table-existence guard needed here, unlike starter.py/offense.py's
    # raw.retrosheet_event checks -- core.player_war is created by a core
    # migration (always present on any migrated database), not a
    # connector-created raw table that might not exist pre-bootstrap. An
    # empty core.player_war just means every LEFT JOIN below resolves to
    # NULL, which is already the correct, honest behavior.
    values_clause = ", ".join(f"('{bref}', '{retro}')" for bref, retro in _BREF_TO_RETRO.items())
    with conn.cursor() as cur:
        cur.execute(read_sql("team_war_update.sql").format(values_clause=values_clause))
        return cur.rowcount


def health_check() -> list[Check]:
    return [check_table_has_rows("gold.game_feature")]
