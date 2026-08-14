-- Expected upcoming games with prior qualifying relief history
WITH sided AS (
    SELECT f.id, f.game_date, f.home_team_id AS team_id, f.home_bullpen_fip AS resolved_fip
    FROM gold.game_feature f
    WHERE f.home_win IS NULL AND f.mlb_game_pk IS NOT NULL
    UNION ALL
    SELECT f.id, f.game_date, f.away_team_id, f.away_bullpen_fip
    FROM gold.game_feature f
    WHERE f.home_win IS NULL AND f.mlb_game_pk IS NOT NULL
)
SELECT count(*) FROM sided s
WHERE EXISTS (
    SELECT 1 FROM core.game g
    JOIN raw.mlb_playbyplay pbp ON pbp.game_pk = g.game_pk
    WHERE g.game_type = 'regular' AND g.game_pk IS NOT NULL
        AND g.game_date < s.game_date
        AND (g.home_team_id = s.team_id OR g.away_team_id = s.team_id)
);
