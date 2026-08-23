MODEL (
  name gold.platoon_splits,
  kind INCREMENTAL_BY_TIME_RANGE (
    time_column game_date
  ),
  cron '@daily',
  grain (game_instance_key)
);

WITH game_starters AS (
    SELECT
        f.game_instance_key,
        f.season,
        f.game_date,
        f.home_team_id,
        f.away_team_id,
        f.home_starter_id,
        f.away_starter_id,
        COALESCE((
            SELECT p_throws FROM raw.statcast_pitch
            WHERE (pitcher = COALESCE(hp.mlbam_id, hp.retro_id, f.home_starter_id::text)) AND p_throws IS NOT NULL
            LIMIT 1
        ), 'R') AS home_starter_throws,
        COALESCE((
            SELECT p_throws FROM raw.statcast_pitch
            WHERE (pitcher = COALESCE(ap.mlbam_id, ap.retro_id, f.away_starter_id::text)) AND p_throws IS NOT NULL
            LIMIT 1
        ), 'R') AS away_starter_throws
    FROM gold.game_feature f
    LEFT JOIN core.player hp ON hp.id = f.home_starter_id
    LEFT JOIN core.player ap ON ap.id = f.away_starter_id
    WHERE f.game_date BETWEEN @start_date AND @end_date
)
SELECT
    gs.game_instance_key,
    gs.season,
    gs.game_date,
    gs.home_team_id,
    gs.away_team_id,
    gs.home_starter_throws,
    gs.away_starter_throws,
    COALESCE(gf.home_woba, 0.320) AS home_offense_woba_vs_lhp,
    COALESCE(gf.away_woba, 0.320) AS away_offense_woba_vs_lhp,
    COALESCE(gf.home_woba, 0.320) AS home_offense_woba_vs_rhp,
    COALESCE(gf.away_woba, 0.320) AS away_offense_woba_vs_rhp,
    ROUND(
        CASE
            WHEN gs.away_starter_throws = 'L' THEN COALESCE(gf.home_woba, 0.320) - COALESCE(gf.away_starter_vs_lhb_woba, 0.320)
            ELSE COALESCE(gf.home_woba, 0.320) - COALESCE(gf.away_starter_vs_rhb_woba, 0.320)
        END,
        3
    ) AS home_platoon_matchup_woba_diff,
    ROUND(
        CASE
            WHEN gs.home_starter_throws = 'L' THEN COALESCE(gf.away_woba, 0.320) - COALESCE(gf.home_starter_vs_lhb_woba, 0.320)
            ELSE COALESCE(gf.away_woba, 0.320) - COALESCE(gf.home_starter_vs_rhb_woba, 0.320)
        END,
        3
    ) AS away_platoon_matchup_woba_diff
FROM game_starters gs
JOIN gold.game_feature gf ON gf.game_instance_key = gs.game_instance_key;
