"""Team wOBA: point-in-time, no-leakage, within-season rolling weighted
on-base average (ADR-036, docs/RESEARCH.md). FanGraphs' own published
formula (their Sabermetrics Library, confirmed via research) --
FanGraphs itself doesn't support scraping or API access (confirmed
directly: their contact page states this explicitly), so this recreates
the calculation from data already ingested rather than fetching theirs.

wOBA = (0.690*uBB + 0.722*HBP + 0.878*1B + 1.242*2B + 1.569*3B + 2.015*HR)
       / (AB + uBB + SF + HBP)

Weights are FanGraphs' current-era published constants, used as a single
fixed set across every season -- FanGraphs' own linear weights actually
shift year to year (published on their "Guts!" page), and reliably
sourcing the exact per-season table failed the same way the FIP constant
lookup did (docs/RESEARCH.md, ADR-034) -- flagged here for the same
reason, so these aren't mistaken for a year-precise reproduction.
Verified anyway before trusting them: computed the real 2023 MLB
league-average wOBA directly from raw.retrosheet_event with these
weights and got .317, matching the real, independently-known 2023 league
value almost exactly.

Reconstructed from raw.retrosheet_event's per-play data (event_cd: 14=
unintentional BB, 16=HBP, 20/21/22/23=1B/2B/3B/HR; ab_fl/sf_fl=at-bat/
sac-fly flags -- all confirmed against real data before use, not assumed
from column names, same discipline as starter.py) rather than raw.
statcast_batter_expected's season-aggregate xwOBA, which would leak
future games mid-season (the same trap ADR-032 flagged for WAR).

wRC+ (park- and league-adjusted) is a natural next step on top of this,
not built here -- needs FanGraphs' "wOBA Scale" constant, which has the
exact same year-varying, hard-to-source problem as the weights above, and
deserves its own verification pass rather than being bolted on. Same
1910-2025 coverage gap as starter.py: raw.retrosheet_event doesn't cover
the current (2026+) season.
"""

import psycopg

from mlb_baseball.db import get_connection
from mlb_baseball.health import Check

# FanGraphs' current-era published wOBA weights (see module docstring for
# why these are fixed, not year-specific).
W_UBB = 0.690
W_HBP = 0.722
W_1B = 0.878
W_2B = 1.242
W_3B = 1.569
W_HR = 2.015

_COMPUTE_SQL = """
WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.retro_game_id,
        g.home_team_id, g.away_team_id
    FROM core.game g
    WHERE g.game_type = 'regular'
),
team_game_stats AS (
    SELECT
        rg.game_id, rg.season, rg.game_date,
        CASE WHEN re.bat_home_id = '1' THEN rg.home_team_id ELSE rg.away_team_id END AS team_id,
        count(*) FILTER (WHERE re.event_cd = '14') AS ubb,
        count(*) FILTER (WHERE re.event_cd = '16') AS hbp,
        count(*) FILTER (WHERE re.event_cd = '20') AS b1,
        count(*) FILTER (WHERE re.event_cd = '21') AS b2,
        count(*) FILTER (WHERE re.event_cd = '22') AS b3,
        count(*) FILTER (WHERE re.event_cd = '23') AS hr,
        count(*) FILTER (WHERE re.ab_fl = 'T') AS ab,
        count(*) FILTER (WHERE re.sf_fl = 'T') AS sf
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    GROUP BY rg.game_id, rg.season, rg.game_date,
        CASE WHEN re.bat_home_id = '1' THEN rg.home_team_id ELSE rg.away_team_id END
),
rolling AS (
    SELECT game_id, team_id,
        SUM(ubb) OVER w AS ubb_sum, SUM(hbp) OVER w AS hbp_sum,
        SUM(b1) OVER w AS b1_sum, SUM(b2) OVER w AS b2_sum,
        SUM(b3) OVER w AS b3_sum, SUM(hr) OVER w AS hr_sum,
        SUM(ab) OVER w AS ab_sum, SUM(sf) OVER w AS sf_sum
    FROM team_game_stats
    WINDOW w AS (
        PARTITION BY team_id, season ORDER BY game_date, game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),
woba AS (
    SELECT game_id, team_id,
        CASE WHEN (ab_sum + ubb_sum + sf_sum + hbp_sum) > 0 THEN
            (%(w_ubb)s * ubb_sum + %(w_hbp)s * hbp_sum + %(w_1b)s * b1_sum
                + %(w_2b)s * b2_sum + %(w_3b)s * b3_sum + %(w_hr)s * hr_sum)
            / (ab_sum + ubb_sum + sf_sum + hbp_sum)
        END AS value
    FROM rolling
)
UPDATE gold.game_feature f
SET home_woba = hw.value, away_woba = aw.value
FROM regular_games rg
LEFT JOIN woba hw ON hw.game_id = rg.game_id AND hw.team_id = rg.home_team_id
LEFT JOIN woba aw ON aw.game_id = rg.game_id AND aw.team_id = rg.away_team_id
WHERE f.game_id = rg.game_id
"""


def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (exists,) = cur.fetchone()
        if not exists:
            return 0
        cur.execute(
            _COMPUTE_SQL,
            {
                "w_ubb": W_UBB,
                "w_hbp": W_HBP,
                "w_1b": W_1B,
                "w_2b": W_2B,
                "w_3b": W_3B,
                "w_hr": W_HR,
            },
        )
        return cur.rowcount


def health_check() -> list[Check]:
    """Real team wOBA has never been observed outside roughly .250-.400
    across MLB history -- catches an inverted or mis-weighted formula the
    same way park.py's own range check does, not a duplicate table-has-
    rows check."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM gold.game_feature "
            "WHERE home_woba IS NOT NULL AND (home_woba < 0.15 OR home_woba > 0.5)"
        )
        (bad,) = cur.fetchone()
    if bad:
        return [Check("home_woba plausible range", False, f"{bad} rows outside 0.15-0.5")]
    return [Check("home_woba plausible range", True, "all computed values within 0.15-0.5")]
