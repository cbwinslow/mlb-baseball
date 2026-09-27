-- Retrosheet tie-out: per-game totals from the regular-season game logs.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
--
-- The game log has no game id; the id every other table uses is the home team,
-- the date (YYYYMMDD) and the game number (0 single game, 1 or 2 doubleheader),
-- checked for 2019 (2,429 distinct ids for 2,429 rows). A duplicate id would
-- fail loudly in the runner, not be merged.
SELECT
    _season AS season,
    h_team || date || game_number AS game_id,
    v_homeruns::integer + h_homeruns::integer AS hr,
    v_strikeouts::integer + h_strikeouts::integer AS k,
    v_walks::integer + h_walks::integer AS bb,
    v_score::integer + h_score::integer AS r,
    1 AS g
FROM raw.retrosheet_gamelog
WHERE _season BETWEEN %(lo)s::text AND %(hi)s::text
ORDER BY 2
