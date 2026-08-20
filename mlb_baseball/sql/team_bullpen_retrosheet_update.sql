WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.game_number, g.retro_game_id,
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
-- Which regular games actually have Retrosheet event coverage at all
-- (issue #29): `regular_games` pulls every core.game row unconditionally,
-- but Retrosheet's own published event-file coverage has a real ~0.85%
-- gap (confirmed against production -- currently entirely the
-- still-in-progress current season, whose event files Retrosheet hasn't
-- published yet; not a parsing bug here). Same join shape as `starters`/
-- `pitcher_game_stats` above -- reused as an existence gate rather than a
-- data source.
covered_games AS (
    SELECT DISTINCT rg.game_id
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
),
-- One row per team per COVERED game, always -- including team-games
-- where no reliever was used at all (rare, but a real possibility with a
-- complete game). Without this backbone, both the rolling-quality window
-- below and the fatigue lookup would silently go NULL for exactly the
-- games that most need an accurate "entering this game" value: a team
-- having zero relief innings IN today's game says nothing about whether
-- their bullpen was worked hard in the days/games before it. An
-- uncovered game gets no row at all here (not a zero-filled one) --
-- COALESCE(..., 0) below is only ever reached for a game we have real
-- event data for, so a genuine zero and "we don't know" stay
-- distinguishable; an uncovered game is excluded from the team's own
-- rolling history entirely, as if it never happened, rather than
-- fabricating a zero that would understate real fatigue/quality.
team_game AS (
    SELECT rg.game_id, rg.season, rg.game_date, rg.game_number, rg.home_team_id AS team_id
    FROM regular_games rg JOIN covered_games cg ON cg.game_id = rg.game_id
    UNION ALL
    SELECT rg.game_id, rg.season, rg.game_date, rg.game_number, rg.away_team_id AS team_id
    FROM regular_games rg JOIN covered_games cg ON cg.game_id = rg.game_id
),
team_relief_game AS (
    SELECT tg.game_id, tg.season, tg.game_date, tg.game_number, tg.team_id,
        COALESCE(sum(ro.k), 0) AS k, COALESCE(sum(ro.bb), 0) AS bb,
        COALESCE(sum(ro.hbp), 0) AS hbp, COALESCE(sum(ro.hr), 0) AS hr,
        COALESCE(sum(ro.bf), 0) AS bf, COALESCE(sum(ro.outs), 0) AS outs
    FROM team_game tg
    LEFT JOIN relief_only ro ON ro.game_id = tg.game_id AND ro.team_id = tg.team_id
    GROUP BY tg.game_id, tg.season, tg.game_date, tg.game_number, tg.team_id
),
-- Quality: season-to-date rolling rates, same no-leakage shape as
-- starter.py (excludes the current game itself). Orders by `game_date,
-- COALESCE(game_number, 0), game_id`, not `game_date, game_id` alone --
-- found by direct audit alongside issue #9 item 6, the same
-- doubleheader-ordering bug team_rate_retrosheet_update.sql had before
-- db97d96 (see that file's header comment): game_id is an insertion-order
-- serial, not the declared game_number, so a doubleheader loaded "second
-- game first" would leak the later game's stats into the earlier game's
-- "entering" value and vice versa. COALESCE(game_number, 0), not
-- `game_number NULLS LAST`: see team_rate_retrosheet_update.sql's own
-- comment (issue #28) -- confirmed against real production `mlb` data that
-- Retrosheet's raw `number` field is genuinely empty for 10,020 games (all
-- 1901-1909), which `NULLS LAST` would sort after its true doubleheader
-- partner regardless of actual order.
rolling_quality AS (
    SELECT game_id, team_id,
        SUM(k) OVER w AS k_sum, SUM(bb) OVER w AS bb_sum, SUM(hbp) OVER w AS hbp_sum,
        SUM(hr) OVER w AS hr_sum, SUM(bf) OVER w AS bf_sum, SUM(outs) OVER w AS outs_sum
    FROM team_relief_game
    WINDOW w AS (
        PARTITION BY team_id, season ORDER BY game_date, COALESCE(game_number, 0), game_id
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
