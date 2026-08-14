-- Actual resolved upcoming bullpen feature count
WITH sided AS (
    SELECT f.id, f.game_date, f.home_team_id AS team_id, f.home_bullpen_fip AS resolved_fip
    FROM gold.game_feature f
    WHERE f.home_win IS NULL AND f.mlb_game_pk IS NOT NULL
    UNION ALL
    SELECT f.id, f.game_date, f.away_team_id, f.away_bullpen_fip
    FROM gold.game_feature f
    WHERE f.home_win IS NULL AND f.mlb_game_pk IS NOT NULL
)
SELECT count(*) FROM sided WHERE resolved_fip IS NOT NULL;
