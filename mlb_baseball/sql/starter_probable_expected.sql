-- Expected resolvable starter ERA count based on qualifying prior appearances
WITH latest_probable AS (
    SELECT DISTINCT ON (game_pk, side) game_pk, side, pitcher_id
    FROM raw.mlb_probable
    WHERE pitcher_id IS NOT NULL
    ORDER BY game_pk, side, _loaded_at DESC
),
sided AS (
    SELECT f.id, f.game_date, lp.pitcher_id,
        CASE WHEN lp.side = 'home' THEN f.home_starter_era ELSE f.away_starter_era END
            AS resolved_era
    FROM gold.game_feature f
    JOIN latest_probable lp ON lp.game_pk = f.mlb_game_pk
    WHERE f.home_win IS NULL
)
SELECT count(*) FROM sided s
WHERE EXISTS (
    SELECT 1 FROM raw.mlb_playbyplay pbp
    JOIN raw.mlb_schedule ms ON ms.game_id = pbp.game_pk
        AND ms.game_date::date < s.game_date AND ms.game_type = 'R'
    WHERE pbp.pitcher_id = s.pitcher_id
);
