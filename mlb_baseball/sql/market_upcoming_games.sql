-- Upcoming (not-yet-played) gold.game_feature rows with a schedule first-pitch
-- time. core.game only holds completed games, so live Kalshi/Polymarket
-- matching has to go through raw.mlb_schedule the same way starter
-- probable-pitcher features do.
--
-- DISTINCT ON mlb_game_pk: schedule is append-only; take the latest loaded
-- observation so a later status scrape does not fan out the join.
SELECT DISTINCT ON (f.mlb_game_pk)
    f.mlb_game_pk,
    f.game_instance_key,
    f.game_date,
    f.home_team_id,
    f.away_team_id,
    ms.game_datetime
FROM gold.game_feature f
INNER JOIN raw.mlb_schedule AS ms ON ms.game_id = f.mlb_game_pk
WHERE f.home_win IS NULL
    AND f.mlb_game_pk IS NOT NULL
    AND NULLIF(ms.game_datetime, '') IS NOT NULL
ORDER BY
    f.mlb_game_pk,
    ms._loaded_at DESC NULLS LAST
