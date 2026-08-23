-- Health check query for Multi-Year Component Park Factors & Environmental Weather (PARK-01, WEA-01).
-- Asserts row coverage and valid physical/mathematical domain bounds.

SELECT
    COUNT(*) AS total_rows,

    -- Non-null counts
    COUNT(park_factor_1yr) AS park_factor_1yr_rows,
    COUNT(park_factor_3yr) AS park_factor_3yr_rows,
    COUNT(park_factor_5yr) AS park_factor_5yr_rows,
    COUNT(park_hr_factor_3yr) AS park_hr_factor_rows,
    COUNT(park_2b_factor_3yr) AS park_2b_factor_rows,
    COUNT(park_3b_factor_3yr) AS park_3b_factor_rows,
    COUNT(park_lhb_hr_factor_3yr) AS park_lhb_hr_factor_rows,
    COUNT(park_rhb_hr_factor_3yr) AS park_rhb_hr_factor_rows,
    COUNT(air_density_index) AS air_density_rows,
    COUNT(effective_wind_speed) AS effective_wind_rows,
    COUNT(wind_direction_label) AS wind_direction_rows,

    -- Out of bounds checks
    COUNT(*) FILTER (
        WHERE park_factor_1yr < 20.0 OR park_factor_1yr > 350.0
           OR park_factor_3yr < 20.0 OR park_factor_3yr > 350.0
           OR park_factor_5yr < 20.0 OR park_factor_5yr > 350.0
           OR park_hr_factor_3yr < 20.0 OR park_hr_factor_3yr > 350.0
           OR park_2b_factor_3yr < 20.0 OR park_2b_factor_3yr > 350.0
           OR park_3b_factor_3yr < 20.0 OR park_3b_factor_3yr > 350.0
           OR park_lhb_hr_factor_3yr < 20.0 OR park_lhb_hr_factor_3yr > 350.0
           OR park_rhb_hr_factor_3yr < 20.0 OR park_rhb_hr_factor_3yr > 350.0
    ) AS park_factor_oob_cnt,

    COUNT(*) FILTER (
        WHERE air_density_index < 50.0 OR air_density_index > 150.0
           OR effective_wind_speed < -50.0 OR effective_wind_speed > 50.0
    ) AS weather_oob_cnt
FROM gold.game_feature;
