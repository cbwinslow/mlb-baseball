-- Health check query for Statcast quality of contact & expected metrics (STA-03).
-- Asserts row coverage and valid mathematical domain bounds.

SELECT
    COUNT(*) AS total_rows,

    -- Non-null counts
    COUNT(home_starter_hard_hit_pct) AS home_starter_hard_hit_rows,
    COUNT(away_starter_hard_hit_pct) AS away_starter_hard_hit_rows,
    COUNT(home_starter_barrel_pct) AS home_starter_barrel_rows,
    COUNT(away_starter_barrel_pct) AS away_starter_barrel_rows,
    COUNT(home_starter_xwoba) AS home_starter_xwoba_rows,
    COUNT(away_starter_xwoba) AS away_starter_xwoba_rows,
    COUNT(home_starter_xba) AS home_starter_xba_rows,
    COUNT(away_starter_xba) AS away_starter_xba_rows,
    COUNT(home_starter_xslg) AS home_starter_xslg_rows,
    COUNT(away_starter_xslg) AS away_starter_xslg_rows,

    COUNT(home_bullpen_hard_hit_pct) AS home_bullpen_hard_hit_rows,
    COUNT(away_bullpen_hard_hit_pct) AS away_bullpen_hard_hit_rows,
    COUNT(home_bullpen_barrel_pct) AS home_bullpen_barrel_rows,
    COUNT(away_bullpen_barrel_pct) AS away_bullpen_barrel_rows,
    COUNT(home_bullpen_xwoba) AS home_bullpen_xwoba_rows,
    COUNT(away_bullpen_xwoba) AS away_bullpen_xwoba_rows,
    COUNT(home_bullpen_xba) AS home_bullpen_xba_rows,
    COUNT(away_bullpen_xba) AS away_bullpen_xba_rows,
    COUNT(home_bullpen_xslg) AS home_bullpen_xslg_rows,
    COUNT(away_bullpen_xslg) AS away_bullpen_xslg_rows,

    COUNT(home_offense_hard_hit_pct) AS home_offense_hard_hit_rows,
    COUNT(away_offense_hard_hit_pct) AS away_offense_hard_hit_rows,
    COUNT(home_offense_barrel_pct) AS home_offense_barrel_rows,
    COUNT(away_offense_barrel_pct) AS away_offense_barrel_rows,
    COUNT(home_offense_xwoba) AS home_offense_xwoba_rows,
    COUNT(away_offense_xwoba) AS away_offense_xwoba_rows,
    COUNT(home_offense_xba) AS home_offense_xba_rows,
    COUNT(away_offense_xba) AS away_offense_xba_rows,
    COUNT(home_offense_xslg) AS home_offense_xslg_rows,
    COUNT(away_offense_xslg) AS away_offense_xslg_rows,

    -- Out of bounds checks
    COUNT(*) FILTER (
        WHERE home_starter_hard_hit_pct < 0.0 OR home_starter_hard_hit_pct > 1.0
           OR away_starter_hard_hit_pct < 0.0 OR away_starter_hard_hit_pct > 1.0
           OR home_starter_barrel_pct < 0.0 OR home_starter_barrel_pct > 1.0
           OR away_starter_barrel_pct < 0.0 OR away_starter_barrel_pct > 1.0
           OR home_starter_xwoba < 0.0 OR home_starter_xwoba > 1.0
           OR away_starter_xwoba < 0.0 OR away_starter_xwoba > 1.0
           OR home_starter_xba < 0.0 OR home_starter_xba > 1.0
           OR away_starter_xba < 0.0 OR away_starter_xba > 1.0
           OR home_starter_xslg < 0.0 OR home_starter_xslg > 4.0
           OR away_starter_xslg < 0.0 OR away_starter_xslg > 4.0
    ) AS starter_oob_cnt,

    COUNT(*) FILTER (
        WHERE home_bullpen_hard_hit_pct < 0.0 OR home_bullpen_hard_hit_pct > 1.0
           OR away_bullpen_hard_hit_pct < 0.0 OR away_bullpen_hard_hit_pct > 1.0
           OR home_bullpen_barrel_pct < 0.0 OR home_bullpen_barrel_pct > 1.0
           OR away_bullpen_barrel_pct < 0.0 OR away_bullpen_barrel_pct > 1.0
           OR home_bullpen_xwoba < 0.0 OR home_bullpen_xwoba > 1.0
           OR away_bullpen_xwoba < 0.0 OR away_bullpen_xwoba > 1.0
           OR home_bullpen_xba < 0.0 OR home_bullpen_xba > 1.0
           OR away_bullpen_xba < 0.0 OR away_bullpen_xba > 1.0
           OR home_bullpen_xslg < 0.0 OR home_bullpen_xslg > 4.0
           OR away_bullpen_xslg < 0.0 OR away_bullpen_xslg > 4.0
    ) AS bullpen_oob_cnt,

    COUNT(*) FILTER (
        WHERE home_offense_hard_hit_pct < 0.0 OR home_offense_hard_hit_pct > 1.0
           OR away_offense_hard_hit_pct < 0.0 OR away_offense_hard_hit_pct > 1.0
           OR home_offense_barrel_pct < 0.0 OR home_offense_barrel_pct > 1.0
           OR away_offense_barrel_pct < 0.0 OR away_offense_barrel_pct > 1.0
           OR home_offense_xwoba < 0.0 OR home_offense_xwoba > 1.0
           OR away_offense_xwoba < 0.0 OR away_offense_xwoba > 1.0
           OR home_offense_xba < 0.0 OR home_offense_xba > 1.0
           OR away_offense_xba < 0.0 OR away_offense_xba > 1.0
           OR home_offense_xslg < 0.0 OR home_offense_xslg > 4.0
           OR away_offense_xslg < 0.0 OR away_offense_xslg > 4.0
    ) AS offense_oob_cnt
FROM gold.game_feature;
