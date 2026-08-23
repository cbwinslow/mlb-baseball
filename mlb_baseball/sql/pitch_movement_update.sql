-- Pitch Movement, Vertical Separation & Batter Discipline (SHP-01).
-- Point-in-time entering metrics for starting pitchers, bullpens, and lineups.

WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.game_number, g.retro_game_id, g.game_pk,
        g.home_team_id, g.away_team_id
    FROM core.game g
    WHERE lower(g.game_type) = 'regular'
),

pitch_daily AS (
    SELECT
        rg.game_id,
        rg.season,
        rg.game_date,
        rg.game_number,
        sp.pitcher AS pitcher_mlbam_id,
        -- Fastball movement (pfx_z in feet * 12 = inches)
        AVG(NULLIF(sp.pfx_z, '')::numeric * 12.0) FILTER (WHERE sp.pitch_type IN ('FF', 'SI', 'FC') AND NULLIF(sp.pfx_z, '') IS NOT NULL) AS fb_ivb_sum,
        count(*) FILTER (WHERE sp.pitch_type IN ('FF', 'SI', 'FC') AND NULLIF(sp.pfx_z, '') IS NOT NULL) AS fb_ivb_cnt,
        -- Breaking ball movement (pfx_z in feet * 12 = inches)
        AVG(NULLIF(sp.pfx_z, '')::numeric * 12.0) FILTER (WHERE sp.pitch_type IN ('CU', 'KC', 'SL', 'ST', 'SV') AND NULLIF(sp.pfx_z, '') IS NOT NULL) AS brk_drop_sum,
        count(*) FILTER (WHERE sp.pitch_type IN ('CU', 'KC', 'SL', 'ST', 'SV') AND NULLIF(sp.pfx_z, '') IS NOT NULL) AS brk_drop_cnt,
        -- Breaking ball spin rate (RPM)
        AVG(NULLIF(sp.release_spin_rate, '')::numeric) FILTER (WHERE sp.pitch_type IN ('CU', 'KC', 'SL', 'ST', 'SV') AND NULLIF(sp.release_spin_rate, '') IS NOT NULL) AS brk_spin_sum,
        count(*) FILTER (WHERE sp.pitch_type IN ('CU', 'KC', 'SL', 'ST', 'SV') AND NULLIF(sp.release_spin_rate, '') IS NOT NULL) AS brk_spin_cnt
    FROM regular_games rg
    JOIN raw.statcast_pitch sp ON sp.game_pk = rg.game_pk
    WHERE NULLIF(sp.pitcher, '') IS NOT NULL
    GROUP BY rg.game_id, rg.season, rg.game_date, rg.game_number, sp.pitcher
),

pitcher_rolling AS (
    SELECT
        game_id,
        pitcher_mlbam_id,
        season,
        game_date,
        SUM(fb_ivb_sum * fb_ivb_cnt) OVER w AS fb_ivb_weighted_sum,
        SUM(fb_ivb_cnt) OVER w AS fb_ivb_total_cnt,
        SUM(brk_drop_sum * brk_drop_cnt) OVER w AS brk_drop_weighted_sum,
        SUM(brk_drop_cnt) OVER w AS brk_drop_total_cnt,
        SUM(brk_spin_sum * brk_spin_cnt) OVER w AS brk_spin_weighted_sum,
        SUM(brk_spin_cnt) OVER w AS brk_spin_total_cnt
    FROM pitch_daily
    WINDOW w AS (
        PARTITION BY pitcher_mlbam_id, season ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),

pitcher_metrics AS (
    SELECT
        game_id,
        pitcher_mlbam_id,
        CASE WHEN fb_ivb_total_cnt >= 10 THEN ROUND(fb_ivb_weighted_sum / fb_ivb_total_cnt, 2) ELSE NULL END AS fastball_ivb_in,
        CASE WHEN brk_drop_total_cnt >= 5 THEN ROUND(brk_drop_weighted_sum / brk_drop_total_cnt, 2) ELSE NULL END AS curve_drop_in,
        CASE
            WHEN fb_ivb_total_cnt >= 10 AND brk_drop_total_cnt >= 5 THEN
                ROUND((fb_ivb_weighted_sum / fb_ivb_total_cnt) - (brk_drop_weighted_sum / brk_drop_total_cnt), 2)
            ELSE NULL
        END AS vert_separation_in,
        CASE WHEN brk_spin_total_cnt >= 5 THEN ROUND(brk_spin_weighted_sum / brk_spin_total_cnt, 0) ELSE NULL END AS spin_rate_rpm
    FROM pitcher_rolling
),

home_starters AS (
    SELECT f.game_id, pm.fastball_ivb_in, pm.curve_drop_in, pm.vert_separation_in, pm.spin_rate_rpm
    FROM gold.game_feature f
    JOIN core.player cp ON cp.id = f.home_starter_id
    JOIN pitcher_metrics pm ON pm.game_id = f.game_id AND pm.pitcher_mlbam_id = cp.mlbam_id::text
),

away_starters AS (
    SELECT f.game_id, pm.fastball_ivb_in, pm.curve_drop_in, pm.vert_separation_in, pm.spin_rate_rpm
    FROM gold.game_feature f
    JOIN core.player cp ON cp.id = f.away_starter_id
    JOIN pitcher_metrics pm ON pm.game_id = f.game_id AND pm.pitcher_mlbam_id = cp.mlbam_id::text
),

-- Bullpen movement aggregates per team
bullpen_daily AS (
    SELECT
        rg.game_id,
        rg.season,
        rg.game_date,
        rg.game_number,
        CASE WHEN sp.inning_topbot = 'Top' THEN rg.home_team_id ELSE rg.away_team_id END AS fielding_team_id,
        AVG(NULLIF(sp.pfx_z, '')::numeric * 12.0) FILTER (WHERE sp.pitch_type IN ('FF', 'SI', 'FC') AND NULLIF(sp.pfx_z, '') IS NOT NULL) AS bp_fb_sum,
        count(*) FILTER (WHERE sp.pitch_type IN ('FF', 'SI', 'FC') AND NULLIF(sp.pfx_z, '') IS NOT NULL) AS bp_fb_cnt,
        AVG(NULLIF(sp.pfx_z, '')::numeric * 12.0) FILTER (WHERE sp.pitch_type IN ('CU', 'KC', 'SL', 'ST', 'SV') AND NULLIF(sp.pfx_z, '') IS NOT NULL) AS bp_brk_sum,
        count(*) FILTER (WHERE sp.pitch_type IN ('CU', 'KC', 'SL', 'ST', 'SV') AND NULLIF(sp.pfx_z, '') IS NOT NULL) AS bp_brk_cnt
    FROM regular_games rg
    JOIN raw.statcast_pitch sp ON sp.game_pk = rg.game_pk
    LEFT JOIN gold.game_feature f ON f.game_id = rg.game_id
    LEFT JOIN core.player hsp ON hsp.id = f.home_starter_id
    LEFT JOIN core.player asp ON asp.id = f.away_starter_id
    WHERE (sp.inning_topbot = 'Top' AND sp.pitcher != COALESCE(hsp.mlbam_id::text, ''))
       OR (sp.inning_topbot = 'Bot' AND sp.pitcher != COALESCE(asp.mlbam_id::text, ''))
    GROUP BY rg.game_id, rg.season, rg.game_date, rg.game_number, fielding_team_id
),

bullpen_rolling AS (
    SELECT
        game_id,
        fielding_team_id,
        CASE
            WHEN SUM(bp_fb_cnt) OVER w >= 10 AND SUM(bp_brk_cnt) OVER w >= 5 THEN
                ROUND((SUM(bp_fb_sum * bp_fb_cnt) OVER w / SUM(bp_fb_cnt) OVER w) -
                      (SUM(bp_brk_sum * bp_brk_cnt) OVER w / SUM(bp_brk_cnt) OVER w), 2)
            ELSE NULL
        END AS bp_vert_separation_in
    FROM bullpen_daily
    WINDOW w AS (
        PARTITION BY fielding_team_id, season ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),

home_bullpens AS (
    SELECT bpr.game_id, bpr.bp_vert_separation_in
    FROM regular_games rg
    JOIN bullpen_rolling bpr ON bpr.game_id = rg.game_id AND bpr.fielding_team_id = rg.home_team_id
),

away_bullpens AS (
    SELECT bpr.game_id, bpr.bp_vert_separation_in
    FROM regular_games rg
    JOIN bullpen_rolling bpr ON bpr.game_id = rg.game_id AND bpr.fielding_team_id = rg.away_team_id
),

-- Team batting discipline on attack zones
batting_daily AS (
    SELECT
        rg.game_id,
        rg.season,
        rg.game_date,
        rg.game_number,
        CASE WHEN sp.inning_topbot = 'Bot' THEN rg.home_team_id ELSE rg.away_team_id END AS batting_team_id,
        count(*) FILTER (WHERE sp.zone IN ('11','12','13','14')) AS chase_pitches_seen,
        count(*) FILTER (WHERE sp.zone IN ('11','12','13','14') AND sp.type IN ('S', 'X', 'F')) AS chase_swings,
        count(*) FILTER (WHERE sp.zone = '5') AS heart_pitches_seen,
        count(*) FILTER (WHERE sp.zone = '5' AND sp.type IN ('S', 'X', 'F')) AS heart_swings
    FROM regular_games rg
    JOIN raw.statcast_pitch sp ON sp.game_pk = rg.game_pk
    GROUP BY rg.game_id, rg.season, rg.game_date, rg.game_number, batting_team_id
),

batting_rolling AS (
    SELECT
        game_id,
        batting_team_id,
        CASE
            WHEN SUM(chase_pitches_seen) OVER w >= 25 THEN
                ROUND(SUM(chase_swings) OVER w::numeric / SUM(chase_pitches_seen) OVER w, 4)
            ELSE NULL
        END AS bat_chase_pct,
        CASE
            WHEN SUM(heart_pitches_seen) OVER w >= 15 THEN
                ROUND(SUM(heart_swings) OVER w::numeric / SUM(heart_pitches_seen) OVER w, 4)
            ELSE NULL
        END AS bat_heart_swing_pct
    FROM batting_daily
    WINDOW w AS (
        PARTITION BY batting_team_id, season ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),

home_batting AS (
    SELECT btr.game_id, btr.bat_chase_pct, btr.bat_heart_swing_pct
    FROM regular_games rg
    JOIN batting_rolling btr ON btr.game_id = rg.game_id AND btr.batting_team_id = rg.home_team_id
),

away_batting AS (
    SELECT btr.game_id, btr.bat_chase_pct, btr.bat_heart_swing_pct
    FROM regular_games rg
    JOIN batting_rolling btr ON btr.game_id = rg.game_id AND btr.batting_team_id = rg.away_team_id
)

UPDATE gold.game_feature f
SET
    home_starter_fastball_ivb_in = hs.fastball_ivb_in,
    away_starter_fastball_ivb_in = as_p.fastball_ivb_in,
    home_starter_curve_drop_in = hs.curve_drop_in,
    away_starter_curve_drop_in = as_p.curve_drop_in,
    home_starter_vert_separation_in = hs.vert_separation_in,
    away_starter_vert_separation_in = as_p.vert_separation_in,
    home_starter_spin_rate_rpm = hs.spin_rate_rpm,
    away_starter_spin_rate_rpm = as_p.spin_rate_rpm,
    home_bullpen_vert_separation_in = hb.bp_vert_separation_in,
    away_bullpen_vert_separation_in = ab.bp_vert_separation_in,
    home_batting_chase_pct = hbt.bat_chase_pct,
    away_batting_chase_pct = abt.bat_chase_pct,
    home_batting_heart_swing_pct = hbt.bat_heart_swing_pct,
    away_batting_heart_swing_pct = abt.bat_heart_swing_pct
FROM regular_games rg
LEFT JOIN home_starters hs ON hs.game_id = rg.game_id
LEFT JOIN away_starters as_p ON as_p.game_id = rg.game_id
LEFT JOIN home_bullpens hb ON hb.game_id = rg.game_id
LEFT JOIN away_bullpens ab ON ab.game_id = rg.game_id
LEFT JOIN home_batting hbt ON hbt.game_id = rg.game_id
LEFT JOIN away_batting abt ON abt.game_id = rg.game_id
WHERE f.game_id = rg.game_id;
