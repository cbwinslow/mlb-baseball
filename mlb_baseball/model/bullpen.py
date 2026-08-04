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
appearance tracking this project doesn't have yet). Computed as a
window RANGE frame over one row per (team, calendar day) -- ADR-042
replaced an earlier lateral-join version (correct, but O(n^2): a fresh
scan of a team's whole history per team-game, 20+ minutes against full
production data) with this collapse-to-day-grain-first version, which
sidesteps the "RANGE frames treat doubleheaders' same-date peer rows
ambiguously" problem by construction -- collapsing to one row per
team-day first means there are no peer rows left to be ambiguous about.

Scope: raw.retrosheet_event covers 1910-2025 only, so compute() above
leaves quality/fatigue NULL for the live 2026 season on its own --
compute_live() (completed 2026 games) and compute_upcoming() (games that
haven't been played yet) close that gap from raw.mlb_playbyplay instead,
the same raw.mlb_playbyplay substitution starter.py/offense.py's own
compute_live() already made (ADR-046/051). FIP_CONSTANT reuses starter.py's
3.10 for the same reason (see that module's docstring) -- kept as its
own module-level constant here rather than importing starter's, since
a divergence in the two constants would be a deliberate future decision,
not an accident two modules should be forced to share.
"""

import psycopg

from mlb_baseball.db import fetch_one
from mlb_baseball.health import Check, check_join_coverage, check_totals_reconcile

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
-- strictly before today's game_date. Collapsed to one row per
-- (team_id, game_date) first -- doubleheaders would otherwise appear as
-- two peer rows on the same date, and a window RANGE frame's "same
-- date" peer-row semantics don't cleanly express "strictly before
-- today" once two games share a date. With a unique date per row, a
-- plain integer RANGE frame (date arithmetic, no interval casting
-- needed) does the whole trailing sum in one sorted pass per team --
-- see ADR-042 for why this replaced an O(n^2) lateral join that took
-- 20+ minutes against full production data (434K team-game rows).
team_day_outs AS (
    SELECT team_id, game_date, sum(outs) AS outs
    FROM team_relief_game
    GROUP BY team_id, game_date
),
team_day_fatigue AS (
    SELECT team_id, game_date,
        SUM(outs) OVER (
            PARTITION BY team_id ORDER BY game_date
            RANGE BETWEEN (%(fatigue_days)s * INTERVAL '1 day') PRECEDING
                AND INTERVAL '1 day' PRECEDING
        ) AS fatigue_outs
    FROM team_day_outs
),
fatigue AS (
    SELECT trg.game_id, trg.team_id, tdf.fatigue_outs
    FROM team_relief_game trg
    JOIN team_day_fatigue tdf ON tdf.team_id = trg.team_id AND tdf.game_date = trg.game_date
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
        (exists,) = fetch_one(cur)
        if not exists:
            return 0
        cur.execute(
            _BUILD_SQL,
            {"fip_constant": FIP_CONSTANT, "fatigue_days": FATIGUE_WINDOW_DAYS},
        )
        return cur.rowcount


# raw.mlb_playbyplay equivalent of _BUILD_SQL (ADR-051, closing the last
# item on docs/RESEARCH.md's feature-engineering backlog -- starter.py and
# offense.py already got this treatment, ADR-046/048). Same shape as
# _BUILD_SQL above -- team_game backbone, rolling window for quality,
# day-grain-collapsed RANGE window for fatigue (ADR-042's fix, still
# needed here even at 2026-only scale: no reason to reintroduce the O(n^2)
# lateral-join pattern that fix replaced) -- just sourced from
# raw.mlb_playbyplay/raw.mlb_schedule instead of
# raw.retrosheet_event/raw.retrosheet_gameinfo, same substitution
# starter.py's compute_live() made. Starter identity uses the same
# first-pitcher-of-half-inning trick starter.py's own compute_live()
# established (DISTINCT ON game_pk, half_inning, earliest at_bat_index) --
# 'top' = home team pitching (visitor batting), 'bottom' = away team
# pitching, the same convention offense.py's compute_live() uses.
# Completed games only (keyed off core.game, which never holds an
# unplayed game) -- see compute_upcoming() below for still-upcoming games.
_LIVE_BUILD_SQL = """
WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.game_pk,
        g.home_team_id, g.away_team_id
    FROM core.game g
    WHERE g.game_type = 'regular' AND g.game_pk IS NOT NULL
),
first_pitcher AS (
    SELECT DISTINCT ON (game_pk, half_inning) game_pk, half_inning, pitcher_id
    FROM raw.mlb_playbyplay
    ORDER BY game_pk, half_inning, at_bat_index::int
),
starters AS (
    SELECT rg.game_id,
        h.pitcher_id AS home_starter_id, a.pitcher_id AS away_starter_id
    FROM regular_games rg
    JOIN first_pitcher h ON h.game_pk = rg.game_pk AND h.half_inning = 'top'
    JOIN first_pitcher a ON a.game_pk = rg.game_pk AND a.half_inning = 'bottom'
),
play_outs AS (
    SELECT game_pk, pitcher_id, half_inning, event_type,
        outs::int - LAG(outs::int, 1, 0) OVER (
            PARTITION BY game_pk, inning, half_inning ORDER BY at_bat_index::int
        ) AS outs_this_play
    FROM raw.mlb_playbyplay
),
pitcher_game_stats AS (
    SELECT rg.game_id, rg.season, rg.game_date,
        (po.half_inning = 'top') AS is_home_pitcher,
        CASE WHEN po.half_inning = 'top' THEN rg.home_team_id ELSE rg.away_team_id END AS team_id,
        po.pitcher_id,
        count(*) FILTER (WHERE po.event_type IN ('strikeout', 'strikeout_double_play')) AS k,
        count(*) FILTER (WHERE po.event_type IN ('walk', 'intent_walk')) AS bb,
        count(*) FILTER (WHERE po.event_type = 'home_run') AS hr,
        count(*) FILTER (WHERE po.event_type NOT IN (
            'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
            'pickoff_1b', 'pickoff_2b', 'pickoff_3b',
            'pickoff_caught_stealing_2b', 'pickoff_caught_stealing_3b',
            'wild_pitch', 'game_advisory'
        )) AS bf,
        sum(po.outs_this_play) AS outs
    FROM regular_games rg
    JOIN play_outs po ON po.game_pk = rg.game_pk
    GROUP BY rg.game_id, rg.season, rg.game_date, po.half_inning,
        rg.home_team_id, rg.away_team_id, po.pitcher_id
),
relief_only AS (
    SELECT pgs.game_id, pgs.team_id, pgs.k, pgs.bb, pgs.hr, pgs.bf, pgs.outs
    FROM pitcher_game_stats pgs
    JOIN starters s ON s.game_id = pgs.game_id
    WHERE pgs.pitcher_id IS DISTINCT FROM
        CASE WHEN pgs.is_home_pitcher THEN s.home_starter_id ELSE s.away_starter_id END
),
team_game AS (
    SELECT game_id, season, game_date, home_team_id AS team_id FROM regular_games
    UNION ALL
    SELECT game_id, season, game_date, away_team_id AS team_id FROM regular_games
),
team_relief_game AS (
    SELECT tg.game_id, tg.season, tg.game_date, tg.team_id,
        COALESCE(sum(ro.k), 0) AS k, COALESCE(sum(ro.bb), 0) AS bb,
        COALESCE(sum(ro.hr), 0) AS hr,
        COALESCE(sum(ro.bf), 0) AS bf, COALESCE(sum(ro.outs), 0) AS outs
    FROM team_game tg
    LEFT JOIN relief_only ro ON ro.game_id = tg.game_id AND ro.team_id = tg.team_id
    GROUP BY tg.game_id, tg.season, tg.game_date, tg.team_id
),
rolling_quality AS (
    SELECT game_id, team_id,
        SUM(k) OVER w AS k_sum, SUM(bb) OVER w AS bb_sum,
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
            (13 * hr_sum + 3 * bb_sum - 2 * k_sum)::numeric / (outs_sum / 3.0) + %(fip_constant)s
        END AS fip
    FROM rolling_quality
),
team_day_outs AS (
    SELECT team_id, game_date, sum(outs) AS outs
    FROM team_relief_game
    GROUP BY team_id, game_date
),
team_day_fatigue AS (
    SELECT team_id, game_date,
        SUM(outs) OVER (
            PARTITION BY team_id ORDER BY game_date
            RANGE BETWEEN (%(fatigue_days)s * INTERVAL '1 day') PRECEDING
                AND INTERVAL '1 day' PRECEDING
        ) AS fatigue_outs
    FROM team_day_outs
),
fatigue AS (
    SELECT trg.game_id, trg.team_id, tdf.fatigue_outs
    FROM team_relief_game trg
    JOIN team_day_fatigue tdf ON tdf.team_id = trg.team_id AND tdf.game_date = trg.game_date
)
UPDATE gold.game_feature f
SET
    home_bullpen_fip = hq.fip, home_bullpen_k_pct = hq.k_pct, home_bullpen_bb_pct = hq.bb_pct,
    home_bullpen_fatigue = hf.fatigue_outs,
    away_bullpen_fip = aq.fip, away_bullpen_k_pct = aq.k_pct, away_bullpen_bb_pct = aq.bb_pct,
    away_bullpen_fatigue = af.fatigue_outs
FROM regular_games rg
LEFT JOIN quality hq ON hq.game_id = rg.game_id AND hq.team_id = rg.home_team_id
LEFT JOIN quality aq ON aq.game_id = rg.game_id AND aq.team_id = rg.away_team_id
LEFT JOIN fatigue hf ON hf.game_id = rg.game_id AND hf.team_id = rg.home_team_id
LEFT JOIN fatigue af ON af.game_id = rg.game_id AND af.team_id = rg.away_team_id
WHERE f.game_id = rg.game_id AND f.home_bullpen_fip IS NULL
"""


def compute_live(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_playbyplay')")
        (exists,) = fetch_one(cur)
        if not exists:
            return 0
        cur.execute(
            _LIVE_BUILD_SQL,
            {"fip_constant": FIP_CONSTANT, "fatigue_days": FATIGUE_WINDOW_DAYS},
        )
        return cur.rowcount


# ADR-051: closes compute_live()'s own remaining gap -- it only ever
# backfills *completed* 2026 games (keyed off core.game, which never holds
# an unplayed game), same limitation ADR-046 documented for starter.py's
# own compute_live() before ADR-048 closed it with compute_probable().
#
# Deliberately NOT a reuse of starter.py's compute_probable() shape,
# despite both closing "the same kind of gap": bullpen quality/fatigue is
# team-level by design (see this module's own docstring on why -- which
# reliever pitches today is an in-game decision made after this feature is
# computed), so unlike an individual starting pitcher it never depends on
# any announcement at all. gold.game_feature.home_team_id/away_team_id are
# already resolved (core.team.id) by features.py for every upcoming row
# straight from raw.mlb_schedule -- no raw.mlb_probable, no core.player
# crosswalk, no "identity resolves but the rate might not" split the way
# starter.py's probable pitcher has. Every upcoming game gets a shot at
# resolving, gated only on whether the team has any qualifying prior 2026
# relief history to roll up.
#
# No team_game backbone here (unlike _LIVE_BUILD_SQL/_BUILD_SQL above): a
# correlated SUM() over relief_only naturally treats a qualifying game
# with zero relief outs as contributing 0, the same as an explicit
# backbone row would -- the only real difference is a team with *zero*
# qualifying games in a window (no relief_only rows at all) resolves NULL
# here instead of an explicit 0. Deliberately accepted as the "leave it
# NULL, don't guess" precedent already used throughout this project,
# rather than building a backbone this small, one-season query doesn't
# need for performance (unlike ADR-042's fix, which existed specifically
# for the 434K-team-game full-historical-scale problem).
_UPCOMING_BUILD_SQL = """
WITH targets AS (
    SELECT f.id AS feature_id, f.game_date, f.home_team_id, f.away_team_id
    FROM gold.game_feature f
    WHERE f.home_win IS NULL AND f.mlb_game_pk IS NOT NULL AND f.home_bullpen_fip IS NULL
),
regular_games AS (
    SELECT g.id AS game_id, g.game_date, g.game_pk, g.home_team_id, g.away_team_id
    FROM core.game g
    WHERE g.game_type = 'regular' AND g.game_pk IS NOT NULL
),
first_pitcher AS (
    SELECT DISTINCT ON (game_pk, half_inning) game_pk, half_inning, pitcher_id
    FROM raw.mlb_playbyplay
    ORDER BY game_pk, half_inning, at_bat_index::int
),
starters AS (
    SELECT rg.game_id,
        h.pitcher_id AS home_starter_id, a.pitcher_id AS away_starter_id
    FROM regular_games rg
    JOIN first_pitcher h ON h.game_pk = rg.game_pk AND h.half_inning = 'top'
    JOIN first_pitcher a ON a.game_pk = rg.game_pk AND a.half_inning = 'bottom'
),
play_outs AS (
    SELECT game_pk, pitcher_id, half_inning, event_type,
        outs::int - LAG(outs::int, 1, 0) OVER (
            PARTITION BY game_pk, inning, half_inning ORDER BY at_bat_index::int
        ) AS outs_this_play
    FROM raw.mlb_playbyplay
),
pitcher_game_stats AS (
    SELECT rg.game_id, rg.game_date,
        (po.half_inning = 'top') AS is_home_pitcher,
        CASE WHEN po.half_inning = 'top' THEN rg.home_team_id ELSE rg.away_team_id END AS team_id,
        po.pitcher_id,
        count(*) FILTER (WHERE po.event_type IN ('strikeout', 'strikeout_double_play')) AS k,
        count(*) FILTER (WHERE po.event_type IN ('walk', 'intent_walk')) AS bb,
        count(*) FILTER (WHERE po.event_type = 'home_run') AS hr,
        count(*) FILTER (WHERE po.event_type NOT IN (
            'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
            'pickoff_1b', 'pickoff_2b', 'pickoff_3b',
            'pickoff_caught_stealing_2b', 'pickoff_caught_stealing_3b',
            'wild_pitch', 'game_advisory'
        )) AS bf,
        sum(po.outs_this_play) AS outs
    FROM regular_games rg
    JOIN play_outs po ON po.game_pk = rg.game_pk
    GROUP BY rg.game_id, rg.game_date, po.half_inning,
        rg.home_team_id, rg.away_team_id, po.pitcher_id
),
relief_only AS (
    SELECT pgs.game_date, pgs.team_id, pgs.k, pgs.bb, pgs.hr, pgs.bf, pgs.outs
    FROM pitcher_game_stats pgs
    JOIN starters s ON s.game_id = pgs.game_id
    WHERE pgs.pitcher_id IS DISTINCT FROM
        CASE WHEN pgs.is_home_pitcher THEN s.home_starter_id ELSE s.away_starter_id END
),
home_quality AS (
    SELECT t.feature_id,
        CASE WHEN sum(r.bf) > 0 THEN sum(r.k)::numeric / sum(r.bf) END AS k_pct,
        CASE WHEN sum(r.bf) > 0 THEN sum(r.bb)::numeric / sum(r.bf) END AS bb_pct,
        CASE WHEN sum(r.outs) > 0 THEN
            (13 * sum(r.hr) + 3 * sum(r.bb) - 2 * sum(r.k))::numeric / (sum(r.outs) / 3.0)
                + %(fip_constant)s
        END AS fip
    FROM targets t
    JOIN relief_only r ON r.team_id = t.home_team_id AND r.game_date < t.game_date
    GROUP BY t.feature_id
),
away_quality AS (
    SELECT t.feature_id,
        CASE WHEN sum(r.bf) > 0 THEN sum(r.k)::numeric / sum(r.bf) END AS k_pct,
        CASE WHEN sum(r.bf) > 0 THEN sum(r.bb)::numeric / sum(r.bf) END AS bb_pct,
        CASE WHEN sum(r.outs) > 0 THEN
            (13 * sum(r.hr) + 3 * sum(r.bb) - 2 * sum(r.k))::numeric / (sum(r.outs) / 3.0)
                + %(fip_constant)s
        END AS fip
    FROM targets t
    JOIN relief_only r ON r.team_id = t.away_team_id AND r.game_date < t.game_date
    GROUP BY t.feature_id
),
home_fatigue AS (
    SELECT t.feature_id, sum(r.outs) AS fatigue_outs
    FROM targets t
    JOIN relief_only r ON r.team_id = t.home_team_id
        AND r.game_date < t.game_date
        AND r.game_date >= t.game_date - %(fatigue_days)s
    GROUP BY t.feature_id
),
away_fatigue AS (
    SELECT t.feature_id, sum(r.outs) AS fatigue_outs
    FROM targets t
    JOIN relief_only r ON r.team_id = t.away_team_id
        AND r.game_date < t.game_date
        AND r.game_date >= t.game_date - %(fatigue_days)s
    GROUP BY t.feature_id
)
UPDATE gold.game_feature f
SET
    home_bullpen_fip = hq.fip, home_bullpen_k_pct = hq.k_pct, home_bullpen_bb_pct = hq.bb_pct,
    home_bullpen_fatigue = hf.fatigue_outs,
    away_bullpen_fip = aq.fip, away_bullpen_k_pct = aq.k_pct, away_bullpen_bb_pct = aq.bb_pct,
    away_bullpen_fatigue = af.fatigue_outs
FROM targets t
LEFT JOIN home_quality hq ON hq.feature_id = t.feature_id
LEFT JOIN away_quality aq ON aq.feature_id = t.feature_id
LEFT JOIN home_fatigue hf ON hf.feature_id = t.feature_id
LEFT JOIN away_fatigue af ON af.feature_id = t.feature_id
WHERE f.id = t.feature_id
"""


def compute_upcoming(conn: psycopg.Connection) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_playbyplay')")
        (exists,) = fetch_one(cur)
        if not exists:
            return 0
        cur.execute(
            _UPCOMING_BUILD_SQL,
            {"fip_constant": FIP_CONSTANT, "fatigue_days": FATIGUE_WINDOW_DAYS},
        )
        return cur.rowcount


# Shared by health_check()'s upcoming-coverage check below (ADR-051) --
# one row per (upcoming game, side), with the feature table's own
# resolved home/away_bullpen_fip attached per side. No core.player
# crosswalk involved anywhere here (unlike starter.py's own analogous
# check, see issue #5) -- bullpen identity is team_id straight from
# gold.game_feature, so that whole bug class doesn't apply to this check.
_UPCOMING_COVERAGE_CTE = """
WITH sided AS (
    SELECT f.id, f.game_date, f.home_team_id AS team_id, f.home_bullpen_fip AS resolved_fip
    FROM gold.game_feature f
    WHERE f.home_win IS NULL AND f.mlb_game_pk IS NOT NULL
    UNION ALL
    SELECT f.id, f.game_date, f.away_team_id, f.away_bullpen_fip
    FROM gold.game_feature f
    WHERE f.home_win IS NULL AND f.mlb_game_pk IS NOT NULL
)
"""

_UPCOMING_ACTUAL_SQL = (
    _UPCOMING_COVERAGE_CTE + "SELECT count(*) FROM sided WHERE resolved_fip IS NOT NULL"
)

# "Expected" here means "this team has at least one qualifying prior 2026
# relief appearance to roll up" -- same tolerance reasoning as starter.py's
# own probable-coverage check (ADR-048): a team's only qualifying prior
# game(s) can legitimately have zero relief outs recorded (e.g. a
# complete-game shutout), which correctly leaves fip NULL despite "having
# a game" by this check's own EXISTS test -- a real, understood edge case,
# not a bug to chase to zero.
_UPCOMING_EXPECTED_SQL = (
    _UPCOMING_COVERAGE_CTE
    + """
    SELECT count(*) FROM sided s
    WHERE EXISTS (
        SELECT 1 FROM core.game g
        JOIN raw.mlb_playbyplay pbp ON pbp.game_pk = g.game_pk
        WHERE g.game_type = 'regular' AND g.game_pk IS NOT NULL
            AND g.game_date < s.game_date
            AND (g.home_team_id = s.team_id OR g.away_team_id = s.team_id)
    )
    """
)


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
        check_join_coverage(
            "upcoming games get a resolved bullpen feature",
            _UPCOMING_ACTUAL_SQL,
            _UPCOMING_EXPECTED_SQL,
            tolerance=5,
        ),
    ]
