-- Retrosheet tie-out: per player-game batting from the box scores (1871-1961 only).
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
-- One copy per game_id, chosen as in tieout_season_box.sql. Box scores carry no
-- plate-appearance count, so pa is not a fact for this source.
WITH games AS (
    SELECT DISTINCT ON (game_id) game_id, _season, _scope
    FROM raw.retrosheet_box_game
    WHERE _season BETWEEN %(lo)s::text AND %(hi)s::text
    ORDER BY game_id, _scope
)
SELECT g._season AS season,
    g.game_id,
    b.id AS player_id,
    sum(b.hr::integer) AS hr,
    sum(b.so::integer) AS k,
    sum(b.bb::integer) AS bb
FROM games g
JOIN raw.retrosheet_box_batting b ON b.game_id = g.game_id AND b._scope = g._scope
GROUP BY g._season, g.game_id, b.id
ORDER BY g.game_id, b.id
