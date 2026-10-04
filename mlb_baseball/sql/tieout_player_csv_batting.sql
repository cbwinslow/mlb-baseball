-- Retrosheet tie-out: per player-game batting from Retrosheet's CSV batting.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
-- 'value' rows only (see tieout_season_csv_batting.sql). Rows are summed per
-- (game, player) in case a player has more than one lineup slot in a game.
-- Cast via ::numeric, not straight ::integer -- see tieout_season_csv_batting.sql
-- for why (1898-1981 formats these columns "N.0").
-- A total is NULL unless every row in the group has a value: the CSV leaves
-- these columns blank for early seasons (b_k blank for most of 1898-1915).
-- Blank is "not recorded", never zero, and a partial sum would under-count.
SELECT
    _season AS season,
    gid AS game_id,
    id AS player_id,
    CASE WHEN count(*) = count(b_pa) THEN sum(b_pa::numeric::integer) END AS pa,
    CASE WHEN count(*) = count(b_k) THEN sum(b_k::numeric::integer) END AS k,
    CASE WHEN count(*) = count(b_w) THEN sum(b_w::numeric::integer) END AS bb,
    CASE WHEN count(*) = count(b_hr) THEN sum(b_hr::numeric::integer) END AS hr,
    CASE WHEN count(*) = count(b_r) THEN sum(b_r::numeric::integer) END AS r
FROM raw.retrosheet_batting
WHERE stattype = 'value'
    AND _season BETWEEN %(lo)s::text AND %(hi)s::text
GROUP BY _season, gid, id
ORDER BY gid, id
