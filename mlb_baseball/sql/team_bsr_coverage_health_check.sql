-- Coverage check (same shape as team_rate_coverage_health_check.sql,
-- issue #32 precedent): the range/gate checks in team_bsr_health_check.sql
-- can only ever catch a value that's present but implausible -- a total
-- join failure (e.g. a mismatched team_id) makes home_sb/away_sb NULL for
-- every row instead, which IS NOT NULL excludes from those counts.
-- home_sb/away_sb are the right target: ungated (always populated
-- whenever the join succeeds, unlike home_wsb/away_wsb which is
-- legitimately NULL below MIN_ATTEMPTS), and home_wsb/away_wsb ride on
-- the same join. "Eligible" is reconstructed the same way
-- team_bsr_retrosheet_update.sql itself defines it -- a team/game is
-- eligible once that team has at least one PRIOR game that season with
-- real Retrosheet event coverage.
--
-- Requires raw.retrosheet_event/retrosheet_gameinfo to exist -- callers
-- must gate on that themselves (same two-table gate as bsr.py::compute).
WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.game_number,
        g.retro_game_id, g.home_team_id, g.away_team_id
    FROM core.game g
    WHERE g.game_type = 'regular'
),
covered_games AS (
    SELECT DISTINCT rg.game_id, rg.season, rg.game_date, rg.game_number,
        rg.home_team_id, rg.away_team_id
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi
        ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    WHERE EXISTS (
        SELECT 1 FROM raw.retrosheet_event re WHERE re.game_id = rg.retro_game_id
    )
),
team_covered AS (
    SELECT game_id, season, game_date, game_number, home_team_id AS team_id
    FROM covered_games
    UNION ALL
    SELECT game_id, season, game_date, game_number, away_team_id AS team_id
    FROM covered_games
),
eligibility AS (
    SELECT game_id, team_id, row_number() OVER w > 1 AS eligible
    FROM team_covered
    WINDOW w AS (
        PARTITION BY team_id, season
        ORDER BY game_date, COALESCE(game_number, 0), game_id
    )
)
SELECT
    count(*) FILTER (WHERE eh.eligible AND f.home_sb IS NULL),
    count(*) FILTER (WHERE ea.eligible AND f.away_sb IS NULL)
FROM gold.game_feature f
JOIN regular_games rg ON rg.game_id = f.game_id
LEFT JOIN eligibility eh ON eh.game_id = f.game_id AND eh.team_id = rg.home_team_id
LEFT JOIN eligibility ea ON ea.game_id = f.game_id AND ea.team_id = rg.away_team_id
