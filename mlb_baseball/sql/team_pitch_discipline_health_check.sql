-- Diagnostic health-check query for plate discipline and pitch sequence rates
-- (PIT-07, ADR-089). Asserts that all computed rates fall strictly within
-- plausible [0.0, 1.0] bounds.

SELECT
    count(*) FILTER (
        WHERE home_starter_csw_pct IS NOT NULL AND (home_starter_csw_pct < 0.0 OR home_starter_csw_pct > 1.0)
    ),
    count(*) FILTER (
        WHERE away_starter_csw_pct IS NOT NULL AND (away_starter_csw_pct < 0.0 OR away_starter_csw_pct > 1.0)
    ),
    count(*) FILTER (
        WHERE home_starter_whiff_pct IS NOT NULL AND (home_starter_whiff_pct < 0.0 OR home_starter_whiff_pct > 1.0)
    ),
    count(*) FILTER (
        WHERE away_starter_whiff_pct IS NOT NULL AND (away_starter_whiff_pct < 0.0 OR away_starter_whiff_pct > 1.0)
    ),
    count(*) FILTER (
        WHERE home_starter_fstrike_pct IS NOT NULL AND (home_starter_fstrike_pct < 0.0 OR home_starter_fstrike_pct > 1.0)
    ),
    count(*) FILTER (
        WHERE away_starter_fstrike_pct IS NOT NULL AND (away_starter_fstrike_pct < 0.0 OR away_starter_fstrike_pct > 1.0)
    ),
    count(*) FILTER (
        WHERE home_bullpen_csw_pct IS NOT NULL AND (home_bullpen_csw_pct < 0.0 OR home_bullpen_csw_pct > 1.0)
    ),
    count(*) FILTER (
        WHERE away_bullpen_csw_pct IS NOT NULL AND (away_bullpen_csw_pct < 0.0 OR away_bullpen_csw_pct > 1.0)
    ),
    count(*) FILTER (
        WHERE home_bullpen_whiff_pct IS NOT NULL AND (home_bullpen_whiff_pct < 0.0 OR home_bullpen_whiff_pct > 1.0)
    ),
    count(*) FILTER (
        WHERE away_bullpen_whiff_pct IS NOT NULL AND (away_bullpen_whiff_pct < 0.0 OR away_bullpen_whiff_pct > 1.0)
    )
FROM gold.game_feature;
