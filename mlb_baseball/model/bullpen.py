"""Bullpen quality and fatigue (ADR-039, docs/RESEARCH.md's
feature-engineering backlog item 7). Research consensus (InsidethePen
usage-tracking analysis) is direct: relievers now handle 40%+ of
innings, WHIP/K%/BB% predict bullpen betting value better than ERA, and
recent workload measurably reduces effectiveness independent of quality.

Team-level, not pitcher-level -- deliberately: which specific relievers
a manager uses today is an in-game decision made after the point this
feature is computed for (before first pitch), so a per-pitcher bullpen
composition feature would leak the very information it's trying to
predict around. Instead this rolls up every relief appearance (any
pitcher credited on a team's plays who wasn't that game's starter, via
resp_pit_id/resp_pit_start_fl -- same fields starter.py already
verified against Chadwick's docs) into a team aggregate, the same
point-in-time rolling shape as starter.py's k_pct/bb_pct: season-to-date,
strictly excluding the current game (ROWS BETWEEN UNBOUNDED PRECEDING
AND 1 PRECEDING).

Fatigue is a second, separate signal from quality: a trailing 3-calendar
-day count of outs recorded by the team's bullpen, a workload proxy for
how taxed the pen is entering today's game. 3 days chosen to match the
"pitches thrown in the last 5 days, back-to-back appearances" workload
window the research above describes, narrowed to what's cheaply and
unambiguously derivable at team grain from event data (a precise
per-pitcher pitch-count/back-to-back signal would need roster-level
appearance tracking this project doesn't have yet). Computed via a
lateral join against each team's own prior relief-outs rows within the
date window, not a window function -- RANGE frames over date-typed
columns handle doubleheader same-date peer rows ambiguously for a
"trailing N calendar days" definition, a plain date-range join is more
direct and auditable here.

Scope: same as starter.py -- raw.retrosheet_event covers 1910-2025 only,
so both quality and fatigue are NULL for the live 2026 season until the
raw.mlb_playbyplay equivalent is built (a separate, already-tracked
follow-up, see docs/RESEARCH.md item 9). FIP_CONSTANT reuses starter.py's
3.10 for the same reason (see that module's docstring) -- kept as its
own module-level constant here rather than importing starter's, since
a divergence in the two constants would be a deliberate future decision,
not an accident two modules should be forced to share.
"""

import psycopg

from mlb_baseball.health import Check, check_totals_reconcile

FIP_CONSTANT = 3.10
FATIGUE_WINDOW_DAYS = 3

_BUILD_SQL = """
WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.retro_game_id,
        g.home_team_id, g.away_team_id
    FROM core.game g
    WHERE g.game_type = 'regular'
),
starters AS (
    SELECT rg.game_id,
        max(re.resp_pit_id) FILTER (WHERE re.bat_home_id = '0') AS home_starter_retro_id,
        max(re.resp_pit_id) FILTER (WHERE re.bat_home_id = '1') AS away_starter_retro_id
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    WHERE re.resp_pit_start_fl = 'T'
    GROUP BY rg.game_id
),
-- Every pitcher appearance (any role), team-attributed via bat_home_id:
-- '0' = away team batting = home team's pitcher on the mound; '1' = the
-- reverse -- same convention starter.py's home/away split already uses.
pitcher_game_stats AS (
    SELECT
        rg.game_id, (re.bat_home_id = '0') AS is_home_pitcher,
        CASE WHEN re.bat_home_id = '0' THEN rg.home_team_id ELSE rg.away_team_id END AS team_id,
        re.resp_pit_id AS pitcher_retro_id,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '3') AS k,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd IN ('14', '15')) AS bb,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '16') AS hbp,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '23') AS hr,
        count(*) FILTER (WHERE re.bat_event_fl = 'T') AS bf,
        sum(re.event_outs_ct::numeric) AS outs
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    GROUP BY rg.game_id, rg.home_team_id, rg.away_team_id, re.bat_home_id, re.resp_pit_id
),
-- Relief only: exclude whichever pitcher started for that team+game.
relief_only AS (
    SELECT pgs.game_id, pgs.team_id, pgs.k, pgs.bb, pgs.hbp, pgs.hr, pgs.bf, pgs.outs
    FROM pitcher_game_stats pgs
    JOIN starters s ON s.game_id = pgs.game_id
    WHERE pgs.pitcher_retro_id IS DISTINCT FROM
        CASE WHEN pgs.is_home_pitcher THEN s.home_starter_retro_id ELSE s.away_starter_retro_id END
),
-- One row per team per game, always -- including team-games where no
-- reliever was used at all (rare, but a real possibility with a complete
-- game). Without this backbone, both the rolling-quality window below
-- and the fatigue lookup would silently go NULL for exactly the games
-- that most need an accurate "entering this game" value: a team having
-- zero relief innings IN today's game says nothing about whether their
-- bullpen was worked hard in the days/games before it.
team_game AS (
    SELECT game_id, season, game_date, home_team_id AS team_id FROM regular_games
    UNION ALL
    SELECT game_id, season, game_date, away_team_id AS team_id FROM regular_games
),
team_relief_game AS (
    SELECT tg.game_id, tg.season, tg.game_date, tg.team_id,
        COALESCE(sum(ro.k), 0) AS k, COALESCE(sum(ro.bb), 0) AS bb,
        COALESCE(sum(ro.hbp), 0) AS hbp, COALESCE(sum(ro.hr), 0) AS hr,
        COALESCE(sum(ro.bf), 0) AS bf, COALESCE(sum(ro.outs), 0) AS outs
    FROM team_game tg
    LEFT JOIN relief_only ro ON ro.game_id = tg.game_id AND ro.team_id = tg.team_id
    GROUP BY tg.game_id, tg.season, tg.game_date, tg.team_id
),
-- Quality: season-to-date rolling rates, same no-leakage shape as
-- starter.py (excludes the current game itself).
rolling_quality AS (
    SELECT game_id, team_id,
        SUM(k) OVER w AS k_sum, SUM(bb) OVER w AS bb_sum, SUM(hbp) OVER w AS hbp_sum,
        SUM(hr) OVER w AS hr_sum, SUM(bf) OVER w AS bf_sum, SUM(outs) OVER w AS outs_sum
    FROM team_relief_game
    WINDOW w AS (
        PARTITION BY team_id, season ORDER BY game_date, game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),
quality AS (
    SELECT game_id, team_id,
        CASE WHEN bf_sum > 0 THEN k_sum::numeric / bf_sum END AS k_pct,
        CASE WHEN bf_sum > 0 THEN bb_sum::numeric / bf_sum END AS bb_pct,
        CASE WHEN outs_sum > 0 THEN
            (13 * hr_sum + 3 * (bb_sum + hbp_sum) - 2 * k_sum)::numeric
                / (outs_sum / 3.0) + %(fip_constant)s
        END AS fip
    FROM rolling_quality
),
-- Fatigue: trailing FATIGUE_WINDOW_DAYS calendar-day sum of relief outs,
-- strictly before today's game_date -- a plain date-range lateral join,
-- not a window RANGE frame (see module docstring for why).
fatigue AS (
    SELECT trg.game_id, trg.team_id, prior.fatigue_outs
    FROM team_relief_game trg
    CROSS JOIN LATERAL (
        SELECT sum(p.outs) AS fatigue_outs
        FROM team_relief_game p
        WHERE p.team_id = trg.team_id
            AND p.game_date >= trg.game_date - %(fatigue_days)s
            AND p.game_date < trg.game_date
    ) prior
)
UPDATE gold.game_feature f
SET
    home_bullpen_fip = hq.fip,
    home_bullpen_k_pct = hq.k_pct,
    home_bullpen_bb_pct = hq.bb_pct,
    home_bullpen_fatigue = hf.fatigue_outs,
    away_bullpen_fip = aq.fip,
    away_bullpen_k_pct = aq.k_pct,
    away_bullpen_bb_pct = aq.bb_pct,
    away_bullpen_fatigue = af.fatigue_outs
FROM regular_games rg
LEFT JOIN quality hq ON hq.game_id = rg.game_id AND hq.team_id = rg.home_team_id
LEFT JOIN quality aq ON aq.game_id = rg.game_id AND aq.team_id = rg.away_team_id
LEFT JOIN fatigue hf ON hf.game_id = rg.game_id AND hf.team_id = rg.home_team_id
LEFT JOIN fatigue af ON af.game_id = rg.game_id AND af.team_id = rg.away_team_id
WHERE f.game_id = rg.game_id
"""


def compute(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        (exists,) = cur.fetchone()
        if not exists:
            return 0
        cur.execute(
            _BUILD_SQL,
            {"fip_constant": FIP_CONSTANT, "fatigue_days": FATIGUE_WINDOW_DAYS},
        )
        return cur.rowcount


def health_check() -> list[Check]:
    """Internal consistency, not an external reconciliation: raw.
    bref_pitching has no team-season total rows to compare against (it's
    strictly per-player, and doesn't split a swingman's starts from
    their relief outings within a season), so unlike starter.py this
    can't validate against an independent source. Instead it checks the
    one thing that actually could be wrong here and would matter: that
    "relief" (every pitcher who wasn't that game's starter) and "starter"
    together are exhaustive and non-overlapping -- i.e. relief outs
    recorded per team-game plus that team's starter's own outs (both
    computed fresh here, not reused from gold.game_feature's stored
    rates) must exactly equal the team's total outs pitched that game,
    tolerance=0. A mismatch would mean a pitcher got mis-classified or
    double-counted, e.g. a bat_home_id or resp_pit_start_fl assumption
    breaking on some real row this wasn't checked against."""
    return [
        check_totals_reconcile(
            "bullpen/starter split: relief + starter outs vs team's total outs pitched",
            """
            WITH regular_games AS (
                SELECT g.id AS game_id, g.retro_game_id, g.home_team_id, g.away_team_id
                FROM core.game g WHERE g.game_type = 'regular'
            ),
            starters AS (
                SELECT rg.game_id,
                    max(re.resp_pit_id) FILTER (WHERE re.bat_home_id = '0') AS home_sp,
                    max(re.resp_pit_id) FILTER (WHERE re.bat_home_id = '1') AS away_sp
                FROM regular_games rg
                JOIN raw.retrosheet_gameinfo gi
                    ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
                JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
                WHERE re.resp_pit_start_fl = 'T'
                GROUP BY rg.game_id
            ),
            team_pitcher_outs AS (
                SELECT rg.game_id,
                    CASE WHEN re.bat_home_id = '0'
                        THEN rg.home_team_id ELSE rg.away_team_id END AS team_id,
                    re.resp_pit_id AS pitcher_retro_id,
                    sum(re.event_outs_ct::numeric) AS outs
                FROM regular_games rg
                JOIN raw.retrosheet_gameinfo gi
                    ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
                JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
                GROUP BY rg.game_id, rg.home_team_id, rg.away_team_id,
                    re.bat_home_id, re.resp_pit_id
            ),
            per_team_game AS (
                SELECT tpo.game_id, tpo.team_id, sum(tpo.outs) AS total_outs,
                    sum(tpo.outs) FILTER (WHERE tpo.pitcher_retro_id = CASE
                        WHEN tpo.team_id = rg.home_team_id THEN s.home_sp ELSE s.away_sp END
                    ) AS starter_outs,
                    sum(tpo.outs) FILTER (WHERE tpo.pitcher_retro_id IS DISTINCT FROM CASE
                        WHEN tpo.team_id = rg.home_team_id THEN s.home_sp ELSE s.away_sp END
                    ) AS relief_outs
                FROM team_pitcher_outs tpo
                JOIN regular_games rg ON rg.game_id = tpo.game_id
                JOIN starters s ON s.game_id = tpo.game_id
                GROUP BY tpo.game_id, tpo.team_id
            )
            SELECT game_id || '-' || team_id, total_outs,
                COALESCE(starter_outs, 0) + COALESCE(relief_outs, 0)
            FROM per_team_game
            """,
            tolerance=0,
        ),
    ]
