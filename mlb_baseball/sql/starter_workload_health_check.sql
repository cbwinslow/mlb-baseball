-- Coverage checked on both home and away sides (issue #9 item 3): the two
-- resolve through the same logic but two different join legs, so an
-- away-only join bug is a real, if unlikely, failure mode a home-only
-- check can't surface. Bounds checks (negative rest/outs) already covered
-- both sides.
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
    ) AS total_may_plus_home_starts,
    count(*) FILTER (
        WHERE away_starter_id IS NOT NULL
        AND EXTRACT(MONTH FROM game_date) >= 5
        AND away_starter_rest_days IS NULL
    ) AS unpopulated_may_plus_away_rest,
    count(*) FILTER (
        WHERE away_starter_id IS NOT NULL
        AND EXTRACT(MONTH FROM game_date) >= 5
    ) AS total_may_plus_away_starts
FROM gold.game_feature
WHERE home_win IS NOT NULL;
