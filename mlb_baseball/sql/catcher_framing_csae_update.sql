-- Catcher Framing and Called Strike Above Expected (CSAE%) & Framing Runs (CAT-02).
-- Point-in-time entering stats for starting catchers strictly prior to the target game.

WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.game_number, g.retro_game_id,
        g.home_team_id, g.away_team_id
    FROM core.game g
    WHERE lower(g.game_type) = 'regular'
),

-- Determine starting catcher per game & fielding half (inn_ct = 1)
starting_catchers AS (
    SELECT DISTINCT ON (rg.game_id, re.bat_home_id)
        rg.game_id,
        rg.season,
        rg.game_date,
        rg.game_number,
        re.bat_home_id,
        re.pos2_fld_id AS catcher_retro_id,
        CASE WHEN re.bat_home_id = '0' THEN rg.home_team_id ELSE rg.away_team_id END AS fielding_team_id
    FROM regular_games rg
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    WHERE NULLIF(re.pos2_fld_id, '') IS NOT NULL
    ORDER BY rg.game_id, re.bat_home_id, re.inn_ct ASC
),

-- Aggregate catcher daily takes and called strikes
catcher_daily AS (
    SELECT
        rg.game_id,
        rg.season,
        rg.game_date,
        rg.game_number,
        re.pos2_fld_id AS catcher_retro_id,
        -- Called strikes (event_cd = '3' or pitch 'C')
        count(*) FILTER (WHERE re.event_cd = '3' OR re.event_tx LIKE '%C%') AS called_strikes,
        -- Total takes (called strikes + balls + walks)
        count(*) FILTER (WHERE re.event_cd IN ('3', '14') OR re.event_tx LIKE '%B%' OR re.event_tx LIKE '%C%') AS total_takes
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    WHERE NULLIF(re.pos2_fld_id, '') IS NOT NULL
    GROUP BY rg.game_id, rg.season, rg.game_date, rg.game_number, re.pos2_fld_id
),

catcher_rolling AS (
    SELECT
        game_id,
        catcher_retro_id,
        season,
        game_date,
        SUM(called_strikes) OVER w AS called_strikes_sum,
        SUM(total_takes) OVER w AS total_takes_sum
    FROM catcher_daily
    WINDOW w AS (
        PARTITION BY catcher_retro_id, season ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),

catcher_metrics AS (
    SELECT
        game_id,
        catcher_retro_id,
        called_strikes_sum,
        total_takes_sum,
        CASE
            WHEN total_takes_sum >= 25 THEN
                ROUND((called_strikes_sum::numeric / total_takes_sum) - 0.3300, 4)
            ELSE NULL
        END AS csae_pct,
        CASE
            WHEN total_takes_sum >= 25 THEN
                ROUND((called_strikes_sum::numeric - (total_takes_sum * 0.3300)) * 0.125, 2)
            ELSE NULL
        END AS framing_runs
    FROM catcher_rolling
),

home_catchers AS (
    SELECT
        sc.game_id,
        cm.csae_pct,
        cm.framing_runs
    FROM starting_catchers sc
    JOIN catcher_metrics cm ON cm.game_id = sc.game_id AND cm.catcher_retro_id = sc.catcher_retro_id
    WHERE sc.bat_home_id = '0' -- home team is fielding
),

away_catchers AS (
    SELECT
        sc.game_id,
        cm.csae_pct,
        cm.framing_runs
    FROM starting_catchers sc
    JOIN catcher_metrics cm ON cm.game_id = sc.game_id AND cm.catcher_retro_id = sc.catcher_retro_id
    WHERE sc.bat_home_id = '1' -- away team is fielding
)

UPDATE gold.game_feature f
SET
    home_catcher_csae_pct = hc.csae_pct,
    away_catcher_csae_pct = ac.csae_pct,
    home_catcher_framing_runs = hc.framing_runs,
    away_catcher_framing_runs = ac.framing_runs
FROM regular_games rg
LEFT JOIN home_catchers hc ON hc.game_id = rg.game_id
LEFT JOIN away_catchers ac ON ac.game_id = rg.game_id
WHERE f.game_id = rg.game_id;
