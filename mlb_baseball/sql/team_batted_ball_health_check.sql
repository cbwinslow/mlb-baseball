-- Health check for gold.game_feature batted-ball metrics.
-- Validates that populated rates fall within [0.0, 1.0].

SELECT
    COUNT(*) AS total_rows,
    COUNT(home_starter_gb_pct) AS populated_starter_gb,
    COUNT(home_starter_fb_pct) AS populated_starter_fb,
    COUNT(home_starter_ld_pct) AS populated_starter_ld,
    COUNT(home_starter_hr_per_fb) AS populated_starter_hr_per_fb,
    COUNT(home_bullpen_gb_pct) AS populated_bullpen_gb,
    COUNT(home_batting_gb_pct) AS populated_batting_gb,
    COUNT(*) FILTER (
        WHERE (home_starter_gb_pct IS NOT NULL AND (home_starter_gb_pct < 0 OR home_starter_gb_pct > 1))
           OR (away_starter_gb_pct IS NOT NULL AND (away_starter_gb_pct < 0 OR away_starter_gb_pct > 1))
           OR (home_starter_fb_pct IS NOT NULL AND (home_starter_fb_pct < 0 OR home_starter_fb_pct > 1))
           OR (away_starter_fb_pct IS NOT NULL AND (away_starter_fb_pct < 0 OR away_starter_fb_pct > 1))
           OR (home_starter_ld_pct IS NOT NULL AND (home_starter_ld_pct < 0 OR home_starter_ld_pct > 1))
           OR (away_starter_ld_pct IS NOT NULL AND (away_starter_ld_pct < 0 OR away_starter_ld_pct > 1))
           OR (home_starter_hr_per_fb IS NOT NULL AND (home_starter_hr_per_fb < 0 OR home_starter_hr_per_fb > 1))
           OR (away_starter_hr_per_fb IS NOT NULL AND (away_starter_hr_per_fb < 0 OR away_starter_hr_per_fb > 1))
           OR (home_bullpen_gb_pct IS NOT NULL AND (home_bullpen_gb_pct < 0 OR home_bullpen_gb_pct > 1))
           OR (away_bullpen_gb_pct IS NOT NULL AND (away_bullpen_gb_pct < 0 OR away_bullpen_gb_pct > 1))
           OR (home_batting_gb_pct IS NOT NULL AND (home_batting_gb_pct < 0 OR home_batting_gb_pct > 1))
           OR (away_batting_gb_pct IS NOT NULL AND (away_batting_gb_pct < 0 OR away_batting_gb_pct > 1))
    ) AS out_of_bounds_count
FROM gold.game_feature;
