-- Coverage checks (issue #32): offense_health_check.sql's range checks can
-- only ever catch a value that's present but out of range -- if a join
-- breaks entirely (e.g. a mismatched team_id), the affected column goes
-- NULL for every row, not out-of-range, and IS NOT NULL excludes NULLs from
-- the count, so the range check reports 0 bad rows even though the feature
-- is completely missing. "Eligible" is reconstructed the same way
-- team_woba_retrosheet_update.sql itself defines it -- a team/game is
-- eligible once that team has at least one PRIOR game that season with
-- real Retrosheet event coverage -- so an eligible row is one where
-- compute() should have produced a real value. home_wrc_plus/away_wrc_plus
-- have no separate per-side join to break (both are computed straight off
-- home_woba/away_woba/park_factor in the same UPDATE, see
-- team_wrc_plus_retrosheet_update.sql) -- their coverage check is simpler:
-- once woba and park_factor are both present, wrc_plus must be too.
--
-- Requires raw.retrosheet_event/retrosheet_gameinfo to exist -- callers
-- must gate on that themselves (same two-table gate as offense.py::compute),
-- since to_regclass('nonexistent') is NULL, not an error, but joining a
-- genuinely nonexistent relation still is.
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
    count(*) FILTER (WHERE eh.eligible AND f.home_woba IS NULL),
    count(*) FILTER (WHERE ea.eligible AND f.away_woba IS NULL),
    count(*) FILTER (
        WHERE f.home_woba IS NOT NULL AND f.park_factor IS NOT NULL
        AND f.home_wrc_plus IS NULL
    ),
    count(*) FILTER (
        WHERE f.away_woba IS NOT NULL AND f.park_factor IS NOT NULL
        AND f.away_wrc_plus IS NULL
    )
FROM gold.game_feature f
JOIN regular_games rg ON rg.game_id = f.game_id
LEFT JOIN eligibility eh ON eh.game_id = f.game_id AND eh.team_id = rg.home_team_id
LEFT JOIN eligibility ea ON ea.game_id = f.game_id AND ea.team_id = rg.away_team_id
