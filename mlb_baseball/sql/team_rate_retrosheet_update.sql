-- Prior rolling team OBP/SLG/ISO/BB%/K% (OFF-01/02/03), same shape as
-- team_woba_retrosheet_update.sql: SUM(...) OVER an UNBOUNDED PRECEDING
-- .. 1 PRECEDING window, so the value entering a game reflects every
-- completed game strictly before it, within the same season.

WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.retro_game_id,
        g.home_team_id, g.away_team_id
    FROM core.game g
    WHERE g.game_type = 'regular'
),
team_game_stats AS (
    SELECT
        rg.game_id, rg.season, rg.game_date,
        CASE WHEN re.bat_home_id = '1' THEN rg.home_team_id ELSE rg.away_team_id END AS team_id,
        count(*) FILTER (WHERE re.event_cd = '14') AS ubb,
        count(*) FILTER (WHERE re.event_cd = '15') AS ibb,
        count(*) FILTER (WHERE re.event_cd = '16') AS hbp,
        count(*) FILTER (WHERE re.event_cd = '20') AS b1,
        count(*) FILTER (WHERE re.event_cd = '21') AS b2,
        count(*) FILTER (WHERE re.event_cd = '22') AS b3,
        count(*) FILTER (WHERE re.event_cd = '23') AS hr,
        count(*) FILTER (WHERE re.event_cd = '3') AS so,
        count(*) FILTER (WHERE re.ab_fl = 'T') AS ab,
        count(*) FILTER (WHERE re.sf_fl = 'T') AS sf
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    GROUP BY rg.game_id, rg.season, rg.game_date,
        CASE WHEN re.bat_home_id = '1' THEN rg.home_team_id ELSE rg.away_team_id END
),
rolling AS (
    SELECT game_id, team_id,
        SUM(ubb) OVER w AS ubb_sum, SUM(ibb) OVER w AS ibb_sum, SUM(hbp) OVER w AS hbp_sum,
        SUM(b1) OVER w AS b1_sum, SUM(b2) OVER w AS b2_sum, SUM(b3) OVER w AS b3_sum,
        SUM(hr) OVER w AS hr_sum, SUM(so) OVER w AS so_sum,
        SUM(ab) OVER w AS ab_sum, SUM(sf) OVER w AS sf_sum
    FROM team_game_stats
    WINDOW w AS (
        PARTITION BY team_id, season ORDER BY game_date, game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),
rate AS (
    SELECT game_id, team_id, ab_sum, hbp_sum, sf_sum, so_sum,
        (b1_sum + b2_sum + b3_sum + hr_sum) AS hits_sum,
        (b1_sum + 2 * b2_sum + 3 * b3_sum + 4 * hr_sum) AS tb_sum,
        (ubb_sum + ibb_sum) AS bb_sum
    FROM rolling
),
computed AS (
    SELECT game_id, team_id,
        CASE WHEN (ab_sum + bb_sum + sf_sum + hbp_sum) > 0 THEN
            (hits_sum + bb_sum + hbp_sum)::numeric / (ab_sum + bb_sum + sf_sum + hbp_sum)
        END AS obp,
        CASE WHEN ab_sum > 0 THEN tb_sum::numeric / ab_sum END AS slg,
        CASE WHEN ab_sum > 0 THEN
            (tb_sum::numeric / ab_sum) - (hits_sum::numeric / ab_sum)
        END AS iso,
        CASE WHEN (ab_sum + bb_sum + sf_sum + hbp_sum) > 0 THEN
            bb_sum::numeric / (ab_sum + bb_sum + sf_sum + hbp_sum)
        END AS bb_pct,
        CASE WHEN (ab_sum + bb_sum + sf_sum + hbp_sum) > 0 THEN
            so_sum::numeric / (ab_sum + bb_sum + sf_sum + hbp_sum)
        END AS k_pct
    FROM rate
)
UPDATE gold.game_feature f
SET home_obp = ch.obp, away_obp = ca.obp,
    home_slg = ch.slg, away_slg = ca.slg,
    home_iso = ch.iso, away_iso = ca.iso,
    home_bb_pct = ch.bb_pct, away_bb_pct = ca.bb_pct,
    home_k_pct = ch.k_pct, away_k_pct = ca.k_pct
FROM regular_games rg
LEFT JOIN computed ch ON ch.game_id = rg.game_id AND ch.team_id = rg.home_team_id
LEFT JOIN computed ca ON ca.game_id = rg.game_id AND ca.team_id = rg.away_team_id
WHERE f.game_id = rg.game_id;
