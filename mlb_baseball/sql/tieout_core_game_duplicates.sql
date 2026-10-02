-- Retrosheet tie-out (core check): core.game rows sharing a retro_game_id, and
-- core.game Retrosheet rows with no game info row (extra in core).
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
SELECT
    cg.season AS season,
    count(*) FILTER (WHERE dup.retro_game_id IS NOT NULL) AS duplicated_rows,
    count(*) FILTER (WHERE gi.gid IS NULL) AS extra_in_core,
    min(cg.retro_game_id) FILTER (WHERE gi.gid IS NULL) AS example_extra
FROM core.game cg
LEFT JOIN (
    SELECT retro_game_id
    FROM core.game
    WHERE retro_game_id IS NOT NULL
    GROUP BY retro_game_id
    HAVING count(*) > 1
) dup ON dup.retro_game_id = cg.retro_game_id
LEFT JOIN raw.retrosheet_gameinfo gi ON gi.gid = cg.retro_game_id
WHERE cg.retro_game_id IS NOT NULL
    AND cg.season BETWEEN %(lo)s AND %(hi)s
GROUP BY cg.season
ORDER BY cg.season
