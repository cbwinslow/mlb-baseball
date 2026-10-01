-- Retrosheet tie-out: per-game totals from the regular-season game logs.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
--
-- The game log has no game id; the id every other table uses is the home team,
-- the date (YYYYMMDD) and the game number (0 single game, 1 or 2 doubleheader),
-- checked for 2019 (2,429 distinct ids for 2,429 rows). A duplicate id would
-- fail loudly in the runner, not be merged.
-- Cast via ::numeric, not straight ::integer, for the four counting stats --
-- see tieout_season_gamelog.sql for why (1901-1979 formats them "N.0").
-- A game with NULL home-run/strikeout/walk counts is kept, with those three
-- facts NULL (not recorded, never compared, never zero) and its score and game
-- count intact, so the game still counts as present in the game log -- see
-- tieout_season_gamelog.sql for the same rows at season grain. All six
-- of v/h_homeruns, v/h_strikeouts, v/h_walks are always NULL together, never
-- partially (verified with no exceptions).
-- A negative home-run/strikeout/walk count is Retrosheet's "not recorded"
-- sentinel (-1), not a count: 1872-1915 has 3,447 games with a -1 strikeout
-- total for a team (checked 2026-10-01, task 4.2). If either team's value for a
-- fact is negative the game's value for that fact is NULL (not recorded, never
-- compared and never summed as -2).
SELECT
    _season AS season,
    h_team || date || game_number AS game_id,
    CASE WHEN v_homeruns::numeric >= 0 AND h_homeruns::numeric >= 0
        THEN v_homeruns::numeric::integer + h_homeruns::numeric::integer END AS hr,
    CASE WHEN v_strikeouts::numeric >= 0 AND h_strikeouts::numeric >= 0
        THEN v_strikeouts::numeric::integer + h_strikeouts::numeric::integer END AS k,
    CASE WHEN v_walks::numeric >= 0 AND h_walks::numeric >= 0
        THEN v_walks::numeric::integer + h_walks::numeric::integer END AS bb,
    v_score::integer + h_score::integer AS r,
    1 AS g
FROM raw.retrosheet_gamelog
WHERE _season BETWEEN %(lo)s::text AND %(hi)s::text
ORDER BY 2
