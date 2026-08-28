-- Health check query for Pitch Movement & Vertical Separation (SHP-01).
-- Asserts row coverage and valid physical bounds.

SELECT
    COUNT(*) AS total_rows,

    COUNT(home_starter_fastball_ivb_in) AS home_starter_ivb_rows,
    COUNT(away_starter_fastball_ivb_in) AS away_starter_ivb_rows,
    COUNT(home_starter_vert_separation_in) AS home_starter_sep_rows,
    COUNT(away_starter_vert_separation_in) AS away_starter_sep_rows,
    COUNT(home_batting_chase_pct) AS home_bat_chase_rows,
    COUNT(away_batting_chase_pct) AS away_bat_chase_rows,

    -- Out of bounds checks
    COUNT(*) FILTER (
        WHERE (home_starter_fastball_ivb_in IS NOT NULL AND (home_starter_fastball_ivb_in < -10.00 OR home_starter_fastball_ivb_in > 35.00))
           OR (away_starter_fastball_ivb_in IS NOT NULL AND (away_starter_fastball_ivb_in < -10.00 OR away_starter_fastball_ivb_in > 35.00))
           OR (home_starter_curve_drop_in IS NOT NULL AND (home_starter_curve_drop_in < -40.00 OR home_starter_curve_drop_in > 25.00))
           OR (away_starter_curve_drop_in IS NOT NULL AND (away_starter_curve_drop_in < -40.00 OR away_starter_curve_drop_in > 25.00))
           OR (home_starter_vert_separation_in IS NOT NULL AND (home_starter_vert_separation_in < -10.00 OR home_starter_vert_separation_in > 50.00))
           OR (away_starter_vert_separation_in IS NOT NULL AND (away_starter_vert_separation_in < -10.00 OR away_starter_vert_separation_in > 50.00))
           OR (home_starter_spin_rate_rpm IS NOT NULL AND (home_starter_spin_rate_rpm < 500 OR home_starter_spin_rate_rpm > 4000))
           OR (away_starter_spin_rate_rpm IS NOT NULL AND (away_starter_spin_rate_rpm < 500 OR away_starter_spin_rate_rpm > 4000))
           OR (home_batting_chase_pct IS NOT NULL AND (home_batting_chase_pct < 0.00 OR home_batting_chase_pct > 1.00))
           OR (away_batting_chase_pct IS NOT NULL AND (away_batting_chase_pct < 0.00 OR away_batting_chase_pct > 1.00))
           OR (home_batting_heart_swing_pct IS NOT NULL AND (home_batting_heart_swing_pct < 0.00 OR home_batting_heart_swing_pct > 1.00))
           OR (away_batting_heart_swing_pct IS NOT NULL AND (away_batting_heart_swing_pct < 0.00 OR away_batting_heart_swing_pct > 1.00))
    ) AS movement_oob_cnt
FROM gold.game_feature;
