SELECT
    count(*) FILTER (WHERE home_starter_rest_days < 0 OR away_starter_rest_days < 0) AS negative_rest_days,
    count(*) FILTER (WHERE home_starter_outs_7d < 0 OR away_starter_outs_7d < 0) AS negative_workload_outs,
    count(*) FILTER (
        WHERE home_starter_id IS NOT NULL
        AND EXTRACT(MONTH FROM game_date) >= 5
        AND home_starter_rest_days IS NULL
    ) AS unpopulated_may_plus_home_rest,
    count(*) FILTER (
        WHERE home_starter_id IS NOT NULL
        AND EXTRACT(MONTH FROM game_date) >= 5
    ) AS total_may_plus_home_starts
FROM gold.game_feature
WHERE home_win IS NOT NULL;
