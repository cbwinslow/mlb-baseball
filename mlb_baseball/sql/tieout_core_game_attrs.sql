-- Retrosheet tie-out (core check): attributes copied into core.game equal raw
-- game info, and no game is duplicated or absent.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
-- The mapping mirrors conform._build_games (conform.py:437-462); see
-- core-lineage.md. Every game, not a sample.
SELECT
    gi._season::integer AS season,
    count(*) AS games,
    count(*) FILTER (WHERE cg.id IS NULL) AS missing_in_core,
    count(*) FILTER (WHERE cg.game_date IS DISTINCT FROM
        to_date(gi.date, 'YYYYMMDD')) AS game_date,
    count(*) FILTER (WHERE cg.season IS DISTINCT FROM gi._season::integer) AS season_col,
    count(*) FILTER (WHERE cg.away_score IS DISTINCT FROM NULLIF(gi.vruns, '')::integer) AS away_score,
    count(*) FILTER (WHERE cg.home_score IS DISTINCT FROM NULLIF(gi.hruns, '')::integer) AS home_score,
    count(*) FILTER (WHERE cg.game_type IS DISTINCT FROM lower(gi.gametype)) AS game_type,
    count(*) FILTER (WHERE cg.site IS DISTINCT FROM gi.site) AS site,
    count(*) FILTER (WHERE cg.day_night IS DISTINCT FROM gi.daynight) AS day_night,
    min(gi.gid) FILTER (WHERE cg.id IS NULL) AS example_missing
FROM raw.retrosheet_gameinfo gi
LEFT JOIN core.game cg ON cg.retro_game_id = gi.gid
WHERE gi._season BETWEEN %(lo)s::text AND %(hi)s::text
GROUP BY gi._season::integer
ORDER BY gi._season::integer
