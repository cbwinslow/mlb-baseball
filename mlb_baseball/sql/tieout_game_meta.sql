-- Retrosheet tie-out: per-game flags from the CSV game info, read only by the
-- register rule E5 (never compared). Read-only. Owner:
-- mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
--
-- exh:  1 when the game info calls the game an exhibition.
-- nogl: 1 when neither club appears in that season's regular-season or
--       post-season game logs at all, so the game is not one the major-league
--       game logs are meant to hold (Negro League clubs, for example).
-- fft:  1 when the game info marks the game a forfeit (forfeit = 'Y'). A
--       forfeit is an awarded score, not a game played, so it has no lineups
--       and no play-by-play.
WITH teams AS (
    SELECT _season AS season, h_team AS team FROM raw.retrosheet_gamelog
    UNION
    SELECT _season, v_team FROM raw.retrosheet_gamelog
    UNION
    SELECT left(date, 4), h_team FROM raw.retrosheet_gamelog_post
    UNION
    SELECT left(date, 4), v_team FROM raw.retrosheet_gamelog_post
)
SELECT
    g._season AS season,
    g.gid AS game_id,
    (lower(g.gametype) = 'exhibition')::integer AS exh,
    (NOT EXISTS (
        SELECT 1 FROM teams t
        WHERE t.season = g._season AND t.team IN (g.hometeam, g.visteam)
    ))::integer AS nogl,
    (g.forfeit = 'Y')::integer AS fft
FROM raw.retrosheet_gameinfo g
WHERE g._season BETWEEN %(lo)s::text AND %(hi)s::text
ORDER BY g.gid
