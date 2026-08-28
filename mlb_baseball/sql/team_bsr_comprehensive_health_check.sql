-- Health check query for Comprehensive Baserunning (RUN-01).
-- Asserts row coverage and valid domain bounds.

SELECT
    COUNT(*) AS total_rows,

    COUNT(home_wsb) AS home_wsb_rows,
    COUNT(away_wsb) AS away_wsb_rows,
    COUNT(home_xbt_pct) AS home_xbt_rows,
    COUNT(away_xbt_pct) AS away_xbt_rows,
    COUNT(home_ubr_runs) AS home_ubr_rows,
    COUNT(away_ubr_runs) AS away_ubr_rows,
    COUNT(home_wgdp_runs) AS home_wgdp_rows,
    COUNT(away_wgdp_runs) AS away_wgdp_rows,
    COUNT(home_bsr_total) AS home_bsr_rows,
    COUNT(away_bsr_total) AS away_bsr_rows,

    -- Out of bounds checks
    COUNT(*) FILTER (
        WHERE (home_wsb IS NOT NULL AND (home_wsb < -20.0 OR home_wsb > 20.0))
           OR (away_wsb IS NOT NULL AND (away_wsb < -20.0 OR away_wsb > 20.0))
           OR (home_xbt_pct IS NOT NULL AND (home_xbt_pct < 0.0 OR home_xbt_pct > 1.0))
           OR (away_xbt_pct IS NOT NULL AND (away_xbt_pct < 0.0 OR away_xbt_pct > 1.0))
           OR (home_ubr_runs IS NOT NULL AND (home_ubr_runs < -20.0 OR home_ubr_runs > 20.0))
           OR (away_ubr_runs IS NOT NULL AND (away_ubr_runs < -20.0 OR away_ubr_runs > 20.0))
           OR (home_bsr_total IS NOT NULL AND (home_bsr_total < -40.0 OR home_bsr_total > 40.0))
           OR (away_bsr_total IS NOT NULL AND (away_bsr_total < -40.0 OR away_bsr_total > 40.0))
    ) AS bsr_oob_cnt
FROM gold.game_feature;
