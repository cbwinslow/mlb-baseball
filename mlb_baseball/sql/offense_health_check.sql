-- Plausible range checks for team wOBA and wRC+
SELECT
    count(*) FILTER (
        WHERE home_woba IS NOT NULL AND (home_woba < 0.02 OR home_woba > 0.70)
    ),
    count(*) FILTER (
        WHERE home_wrc_plus IS NOT NULL AND (home_wrc_plus < 20 OR home_wrc_plus > 250)
    )
FROM gold.game_feature;
