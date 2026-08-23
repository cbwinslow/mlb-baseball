-- Health check query for Strike Zone Command and Attack Zone Metrics (COM-01).
-- Asserts row coverage and valid domain bounds.

SELECT
    COUNT(*) AS total_rows,

    COUNT(home_starter_heart_pct) AS home_starter_heart_rows,
    COUNT(away_starter_heart_pct) AS away_starter_heart_rows,
    COUNT(home_starter_fastball_velo) AS home_starter_velo_rows,
    COUNT(away_starter_fastball_velo) AS away_starter_velo_rows,
    COUNT(home_bullpen_heart_pct) AS home_bp_heart_rows,
    COUNT(away_bullpen_heart_pct) AS away_bp_heart_rows,

    -- Out of bounds checks
    COUNT(*) FILTER (
        WHERE (home_starter_heart_pct IS NOT NULL AND (home_starter_heart_pct < 0.00 OR home_starter_heart_pct > 1.00))
           OR (away_starter_heart_pct IS NOT NULL AND (away_starter_heart_pct < 0.00 OR away_starter_heart_pct > 1.00))
           OR (home_starter_shadow_pct IS NOT NULL AND (home_starter_shadow_pct < 0.00 OR home_starter_shadow_pct > 1.00))
           OR (away_starter_shadow_pct IS NOT NULL AND (away_starter_shadow_pct < 0.00 OR away_starter_shadow_pct > 1.00))
           OR (home_starter_chase_pct IS NOT NULL AND (home_starter_chase_pct < 0.00 OR home_starter_chase_pct > 1.00))
           OR (away_starter_chase_pct IS NOT NULL AND (away_starter_chase_pct < 0.00 OR away_starter_chase_pct > 1.00))
           OR (home_starter_fastball_velo IS NOT NULL AND (home_starter_fastball_velo < 60.00 OR home_starter_fastball_velo > 110.00))
           OR (away_starter_fastball_velo IS NOT NULL AND (away_starter_fastball_velo < 60.00 OR away_starter_fastball_velo > 110.00))
           OR (home_starter_velo_delta IS NOT NULL AND (home_starter_velo_delta < 0.00 OR home_starter_velo_delta > 30.00))
           OR (away_starter_velo_delta IS NOT NULL AND (away_starter_velo_delta < 0.00 OR away_starter_velo_delta > 30.00))
           OR (home_bullpen_heart_pct IS NOT NULL AND (home_bullpen_heart_pct < 0.00 OR home_bullpen_heart_pct > 1.00))
           OR (away_bullpen_heart_pct IS NOT NULL AND (away_bullpen_heart_pct < 0.00 OR away_bullpen_heart_pct > 1.00))
    ) AS command_oob_cnt
FROM gold.game_feature;
