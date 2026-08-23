-- Health check query for Starting Catcher Framing & CSAE% (CAT-02).
-- Asserts row coverage and valid domain bounds.

SELECT
    COUNT(*) AS total_rows,

    COUNT(home_catcher_csae_pct) AS home_csae_rows,
    COUNT(away_catcher_csae_pct) AS away_csae_rows,
    COUNT(home_catcher_framing_runs) AS home_framing_rows,
    COUNT(away_catcher_framing_runs) AS away_framing_rows,

    -- Out of bounds checks
    COUNT(*) FILTER (
        WHERE (home_catcher_csae_pct IS NOT NULL AND (home_catcher_csae_pct < -0.30 OR home_catcher_csae_pct > 0.30))
           OR (away_catcher_csae_pct IS NOT NULL AND (away_catcher_csae_pct < -0.30 OR away_catcher_csae_pct > 0.30))
           OR (home_catcher_framing_runs IS NOT NULL AND (home_catcher_framing_runs < -30.0 OR home_catcher_framing_runs > 30.0))
           OR (away_catcher_framing_runs IS NOT NULL AND (away_catcher_framing_runs < -30.0 OR away_catcher_framing_runs > 30.0))
    ) AS framing_oob_cnt
FROM gold.game_feature;
