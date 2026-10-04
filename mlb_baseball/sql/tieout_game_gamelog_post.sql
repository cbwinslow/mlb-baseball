-- Retrosheet tie-out: per-game totals from the postseason and all-star game logs.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
-- Third source for register entry E1; same game id construction as
-- tieout_game_gamelog.sql. The season is the year of the date.
SELECT
    left(date, 4) AS season,
    h_team || date || game_number AS game_id,
    v_homeruns::integer + h_homeruns::integer AS hr,
    v_strikeouts::integer + h_strikeouts::integer AS k,
    v_walks::integer + h_walks::integer AS bb,
    v_score::integer + h_score::integer AS r,
    1 AS g
FROM raw.retrosheet_gamelog_post
WHERE left(date, 4) BETWEEN %(lo)s::text AND %(hi)s::text
ORDER BY 2
