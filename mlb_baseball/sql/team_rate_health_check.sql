-- Diagnostic health-check query for team prior rate statistics (ADR-061/062/063)
SELECT
    count(*) FILTER (
        WHERE home_obp IS NOT NULL AND (home_obp < 0 OR home_obp > 1)
    ),
    count(*) FILTER (
        WHERE home_slg IS NOT NULL AND (home_slg < 0 OR home_slg > 4)
    ),
    count(*) FILTER (
        WHERE home_iso IS NOT NULL AND (home_iso < 0 OR home_iso > 3)
    ),
    count(*) FILTER (
        WHERE home_babip IS NOT NULL AND (home_babip < 0 OR home_babip > 1)
    ),
    count(*) FILTER (
        WHERE home_bb_pct IS NOT NULL AND (home_bb_pct < 0 OR home_bb_pct > 1)
    ),
    count(*) FILTER (
        WHERE home_k_pct IS NOT NULL AND (home_k_pct < 0 OR home_k_pct > 1)
    ),
    count(*) FILTER (
        WHERE home_runs_for_avg IS NOT NULL
        AND (home_runs_for_avg < 0 OR home_runs_for_avg > 30)
    ),
    count(*) FILTER (
        WHERE home_runs_allowed_avg IS NOT NULL
        AND (home_runs_allowed_avg < 0 OR home_runs_allowed_avg > 30)
    ),
    count(*) FILTER (
        WHERE home_obp IS NOT NULL AND (home_pa IS NULL OR home_pa < %(min_pa)s)
    ),
    count(*) FILTER (
        WHERE home_pa IS NOT NULL AND home_pa < 0
    )
FROM gold.game_feature;
