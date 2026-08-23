MODEL (
    name gold.pitcher_command,
    kind FULL,
    cron '@daily',
    grain [game_id]
);

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
        count(*) AS total_pitches,
        count(*) FILTER (WHERE sp.zone IN ('5') OR (sp.zone IN ('1','2','3','4','6','7','8','9') AND sp.pitch_number::int = 1)) AS heart_pitches,
        count(*) FILTER (WHERE sp.zone IN ('1','2','3','4','6','7','8','9') AND sp.zone != '5') AS shadow_pitches,
        count(*) FILTER (WHERE sp.zone IN ('11','12','13','14')) AS chase_pitches,
        AVG(NULLIF(sp.release_speed, '')::numeric) FILTER (WHERE sp.pitch_type IN ('FF', 'SI', 'FC')) AS fb_velo_sum,
        count(*) FILTER (WHERE sp.pitch_type IN ('FF', 'SI', 'FC') AND NULLIF(sp.release_speed, '') IS NOT NULL) AS fb_velo_cnt,
        AVG(NULLIF(sp.release_speed, '')::numeric) FILTER (WHERE sp.pitch_type IN ('CH', 'FS', 'SL', 'CU', 'ST', 'SV')) AS off_velo_sum,
        count(*) FILTER (WHERE sp.pitch_type IN ('CH', 'FS', 'SL', 'CU', 'ST', 'SV') AND NULLIF(sp.release_speed, '') IS NOT NULL) AS off_velo_cnt
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
        SUM(total_pitches) OVER w AS total_pitches_sum,
        SUM(heart_pitches) OVER w AS heart_pitches_sum,
        SUM(shadow_pitches) OVER w AS shadow_pitches_sum,
        SUM(chase_pitches) OVER w AS chase_pitches_sum,
        SUM(fb_velo_sum * fb_velo_cnt) OVER w AS fb_velo_weighted_sum,
        SUM(fb_velo_cnt) OVER w AS fb_velo_total_cnt,
        SUM(off_velo_sum * off_velo_cnt) OVER w AS off_velo_weighted_sum,
        SUM(off_velo_cnt) OVER w AS off_velo_total_cnt
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
        CASE WHEN total_pitches_sum >= 20 THEN ROUND(heart_pitches_sum::numeric / total_pitches_sum, 4) ELSE NULL END AS heart_pct,
        CASE WHEN total_pitches_sum >= 20 THEN ROUND(shadow_pitches_sum::numeric / total_pitches_sum, 4) ELSE NULL END AS shadow_pct,
        CASE WHEN total_pitches_sum >= 20 THEN ROUND(chase_pitches_sum::numeric / total_pitches_sum, 4) ELSE NULL END AS chase_pct,
        CASE WHEN fb_velo_total_cnt >= 10 THEN ROUND(fb_velo_weighted_sum / fb_velo_total_cnt, 2) ELSE NULL END AS fastball_velo,
        CASE
            WHEN fb_velo_total_cnt >= 10 AND off_velo_total_cnt >= 5 THEN
                ROUND((fb_velo_weighted_sum / fb_velo_total_cnt) - (off_velo_weighted_sum / off_velo_total_cnt), 2)
            ELSE NULL
        END AS velo_delta
    FROM pitcher_rolling
),

home_starters AS (
    SELECT
        f.game_id,
        pm.heart_pct,
        pm.shadow_pct,
        pm.chase_pct,
        pm.fastball_velo,
        pm.velo_delta
    FROM gold.game_feature f
    JOIN core.player cp ON cp.id = f.home_starter_id
    JOIN pitcher_metrics pm ON pm.game_id = f.game_id AND pm.pitcher_mlbam_id = cp.mlbam_id::text
),

away_starters AS (
    SELECT
        f.game_id,
        pm.heart_pct,
        pm.shadow_pct,
        pm.chase_pct,
        pm.fastball_velo,
        pm.velo_delta
    FROM gold.game_feature f
    JOIN core.player cp ON cp.id = f.away_starter_id
    JOIN pitcher_metrics pm ON pm.game_id = f.game_id AND pm.pitcher_mlbam_id = cp.mlbam_id::text
),

bullpen_daily AS (
    SELECT
        rg.game_id,
        rg.season,
        rg.game_date,
        rg.game_number,
        CASE WHEN sp.inning_topbot = 'Top' THEN rg.home_team_id ELSE rg.away_team_id END AS fielding_team_id,
        count(*) AS bp_pitches,
        count(*) FILTER (WHERE sp.zone = '5') AS bp_heart,
        count(*) FILTER (WHERE sp.zone IN ('1','2','3','4','6','7','8','9') AND sp.zone != '5') AS bp_shadow,
        count(*) FILTER (WHERE sp.zone IN ('11','12','13','14')) AS bp_chase
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
            WHEN SUM(bp_pitches) OVER w >= 25 THEN
                ROUND(SUM(bp_heart) OVER w::numeric / SUM(bp_pitches) OVER w, 4)
            ELSE NULL
        END AS bp_heart_pct,
        CASE
            WHEN SUM(bp_pitches) OVER w >= 25 THEN
                ROUND(SUM(bp_shadow) OVER w::numeric / SUM(bp_pitches) OVER w, 4)
            ELSE NULL
        END AS bp_shadow_pct,
        CASE
            WHEN SUM(bp_pitches) OVER w >= 25 THEN
                ROUND(SUM(bp_chase) OVER w::numeric / SUM(bp_pitches) OVER w, 4)
            ELSE NULL
        END AS bp_chase_pct
    FROM bullpen_daily
    WINDOW w AS (
        PARTITION BY fielding_team_id, season ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),

home_bullpens AS (
    SELECT bpr.game_id, bpr.bp_heart_pct, bpr.bp_shadow_pct, bpr.bp_chase_pct
    FROM regular_games rg
    JOIN bullpen_rolling bpr ON bpr.game_id = rg.game_id AND bpr.fielding_team_id = rg.home_team_id
),

away_bullpens AS (
    SELECT bpr.game_id, bpr.bp_heart_pct, bpr.bp_shadow_pct, bpr.bp_chase_pct
    FROM regular_games rg
    JOIN bullpen_rolling bpr ON bpr.game_id = rg.game_id AND bpr.fielding_team_id = rg.away_team_id
)

SELECT
    rg.game_id,
    hs.heart_pct AS home_starter_heart_pct,
    as_p.heart_pct AS away_starter_heart_pct,
    hs.shadow_pct AS home_starter_shadow_pct,
    as_p.shadow_pct AS away_starter_shadow_pct,
    hs.chase_pct AS home_starter_chase_pct,
    as_p.chase_pct AS away_starter_chase_pct,
    hs.fastball_velo AS home_starter_fastball_velo,
    as_p.fastball_velo AS away_starter_fastball_velo,
    hs.velo_delta AS home_starter_velo_delta,
    as_p.velo_delta AS away_starter_velo_delta,
    hb.bp_heart_pct AS home_bullpen_heart_pct,
    ab.bp_heart_pct AS away_bullpen_heart_pct,
    hb.bp_shadow_pct AS home_bullpen_shadow_pct,
    ab.bp_shadow_pct AS away_bullpen_shadow_pct,
    hb.bp_chase_pct AS home_bullpen_chase_pct,
    ab.bp_chase_pct AS away_bullpen_chase_pct
FROM regular_games rg
LEFT JOIN home_starters hs ON hs.game_id = rg.game_id
LEFT JOIN away_starters as_p ON as_p.game_id = rg.game_id
LEFT JOIN home_bullpens hb ON hb.game_id = rg.game_id
LEFT JOIN away_bullpens ab ON ab.game_id = rg.game_id;
