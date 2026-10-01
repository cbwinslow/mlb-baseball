-- Retrosheet tie-out: per-game totals from the regular-season game logs.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
--
-- The game log has no game id; the id every other table uses is the home team,
-- the date (YYYYMMDD) and the game number (0 single game, 1 or 2 doubleheader),
-- checked for 2019 (2,429 distinct ids for 2,429 rows). A duplicate id would
-- fail loudly in the runner, not be merged.
-- Cast via ::numeric, not straight ::integer, for the four counting stats --
-- see tieout_season_gamelog.sql for why (1901-1979 formats them "N.0").
-- A game with NULL home-run/strikeout/walk counts is excluded entirely (not
-- comparable via gamelog for this one game) rather than treated as zero --
-- see tieout_season_gamelog.sql for the same rows at season grain. All six
-- of v/h_homeruns, v/h_strikeouts, v/h_walks are always NULL together, never
-- partially (verified with no exceptions), so checking one is enough.
SELECT
    _season AS season,
    h_team || date || game_number AS game_id,
    v_homeruns::numeric::integer + h_homeruns::numeric::integer AS hr,
    v_strikeouts::numeric::integer + h_strikeouts::numeric::integer AS k,
    v_walks::numeric::integer + h_walks::numeric::integer AS bb,
    v_score::integer + h_score::integer AS r,
    1 AS g
FROM raw.retrosheet_gamelog
WHERE _season BETWEEN %(lo)s::text AND %(hi)s::text
    AND v_homeruns IS NOT NULL
ORDER BY 2
