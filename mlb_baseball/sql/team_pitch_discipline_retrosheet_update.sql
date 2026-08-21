-- Computes entering-game plate discipline and pitch sequence metrics from
-- raw.retrosheet_event.pitch_seq_tx for starting pitchers and bullpens.
--
-- Point-in-time safety: every value is an entering rate computed strictly
-- from games preceding the target game. Doubleheaders are ordered
-- chronologically by COALESCE(g.game_number, 0).
--
-- Pitch code definitions from Retrosheet specifications:
--   C: Called strike
--   S: Swinging strike
--   M: Missed bunt (swinging strike)
--   F, L, T, O: Fouls / foul bunts / foul tips
--   X: Ball put in play by batter
--   B, I, P, V: Balls / intentional balls / pitchouts

WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.game_number, g.retro_game_id,
        g.home_team_id, g.away_team_id
    FROM core.game g
    WHERE g.game_type = 'regular'
),
clean_events AS (
    SELECT
        rg.game_id,
        rg.season,
        rg.game_date,
        rg.game_number,
        rg.home_team_id,
        rg.away_team_id,
        re.resp_pit_id AS pitcher_retro_id,
        re.resp_pit_start_fl,
        CASE WHEN re.bat_home_id = '0' THEN rg.home_team_id ELSE rg.away_team_id END AS pitching_team_id,
        re.bat_home_id,
        LENGTH(REGEXP_REPLACE(re.pitch_seq_tx, '[^BCFKLMOPSTUVWXI]', '', 'g')) AS pitch_count,
        LENGTH(REGEXP_REPLACE(REGEXP_REPLACE(re.pitch_seq_tx, '[^BCFKLMOPSTUVWXI]', '', 'g'), '[^CSM]', '', 'g')) AS csw_count,
        LENGTH(REGEXP_REPLACE(REGEXP_REPLACE(re.pitch_seq_tx, '[^BCFKLMOPSTUVWXI]', '', 'g'), '[^SM]', '', 'g')) AS whiff_count,
        LENGTH(REGEXP_REPLACE(REGEXP_REPLACE(re.pitch_seq_tx, '[^BCFKLMOPSTUVWXI]', '', 'g'), '[^SMFLTOX]', '', 'g')) AS swing_count,
        CASE
            WHEN SUBSTRING(REGEXP_REPLACE(re.pitch_seq_tx, '[^BCFKLMOPSTUVWXI]', '', 'g') FROM 1 FOR 1) ~ '[CSFKTMLOX]' THEN 1
            ELSE 0
        END AS is_fstrike,
        CASE WHEN re.bat_event_fl = 'T' THEN 1 ELSE 0 END AS is_pa
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    WHERE re.pitch_seq_tx IS NOT NULL AND re.pitch_seq_tx != ''
),
pitcher_game_stats AS (
    SELECT
        game_id,
        season,
        game_date,
        game_number,
        pitcher_retro_id,
        SUM(pitch_count) AS pitches,
        SUM(csw_count) AS csw,
        SUM(whiff_count) AS whiffs,
        SUM(swing_count) AS swings,
        SUM(is_fstrike) AS fstrikes,
        SUM(is_pa) AS pa
    FROM clean_events
    GROUP BY game_id, season, game_date, game_number, pitcher_retro_id
),
bullpen_game_stats AS (
    SELECT
        game_id,
        season,
        game_date,
        game_number,
        pitching_team_id AS team_id,
        SUM(pitch_count) AS pitches,
        SUM(csw_count) AS csw,
        SUM(whiff_count) AS whiffs,
        SUM(swing_count) AS swings
    FROM clean_events
    WHERE resp_pit_start_fl = 'F'
    GROUP BY game_id, season, game_date, game_number, pitching_team_id
),
starters AS (
    SELECT
        rg.game_id,
        max(re.resp_pit_id) FILTER (WHERE re.bat_home_id = '0') AS home_starter_retro_id,
        max(re.resp_pit_id) FILTER (WHERE re.bat_home_id = '1') AS away_starter_retro_id
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    WHERE re.resp_pit_start_fl = 'T'
    GROUP BY rg.game_id
),
starter_rolling AS (
    SELECT
        game_id,
        pitcher_retro_id,
        SUM(pitches) OVER w_season AS pitches_sum,
        SUM(csw) OVER w_season AS csw_sum,
        SUM(whiffs) OVER w_season AS whiffs_sum,
        SUM(swings) OVER w_season AS swings_sum,
        SUM(fstrikes) OVER w_season AS fstrikes_sum,
        SUM(pa) OVER w_season AS pa_sum
    FROM pitcher_game_stats
    WINDOW w_season AS (
        PARTITION BY pitcher_retro_id, season
        ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),
bullpen_rolling AS (
    SELECT
        game_id,
        team_id,
        SUM(pitches) OVER w_season AS pitches_sum,
        SUM(csw) OVER w_season AS csw_sum,
        SUM(whiffs) OVER w_season AS whiffs_sum,
        SUM(swings) OVER w_season AS swings_sum
    FROM bullpen_game_stats
    WINDOW w_season AS (
        PARTITION BY team_id, season
        ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),
starter_rates AS (
    SELECT
        game_id,
        pitcher_retro_id,
        CASE WHEN pitches_sum >= %(min_starter_pitches)s THEN csw_sum::numeric / pitches_sum END AS csw_pct,
        CASE WHEN swings_sum >= %(min_starter_swings)s THEN whiffs_sum::numeric / swings_sum END AS whiff_pct,
        CASE WHEN pa_sum >= %(min_starter_pa)s THEN fstrikes_sum::numeric / pa_sum END AS fstrike_pct
    FROM starter_rolling
),
bullpen_rates AS (
    SELECT
        game_id,
        team_id,
        CASE WHEN pitches_sum >= %(min_bullpen_pitches)s THEN csw_sum::numeric / pitches_sum END AS csw_pct,
        CASE WHEN swings_sum >= %(min_bullpen_swings)s THEN whiffs_sum::numeric / swings_sum END AS whiff_pct
    FROM bullpen_rolling
)
UPDATE gold.game_feature f
SET
    home_starter_csw_pct = hsq.csw_pct,
    home_starter_whiff_pct = hsq.whiff_pct,
    home_starter_fstrike_pct = hsq.fstrike_pct,
    away_starter_csw_pct = asq.csw_pct,
    away_starter_whiff_pct = asq.whiff_pct,
    away_starter_fstrike_pct = asq.fstrike_pct,
    home_bullpen_csw_pct = hbq.csw_pct,
    home_bullpen_whiff_pct = hbq.whiff_pct,
    away_bullpen_csw_pct = abq.csw_pct,
    away_bullpen_whiff_pct = abq.whiff_pct
FROM regular_games rg
LEFT JOIN starters s ON s.game_id = rg.game_id
LEFT JOIN starter_rates hsq ON hsq.game_id = rg.game_id AND hsq.pitcher_retro_id = s.home_starter_retro_id
LEFT JOIN starter_rates asq ON asq.game_id = rg.game_id AND asq.pitcher_retro_id = s.away_starter_retro_id
LEFT JOIN bullpen_rates hbq ON hbq.game_id = rg.game_id AND hbq.team_id = rg.home_team_id
LEFT JOIN bullpen_rates abq ON abq.game_id = rg.game_id AND abq.team_id = rg.away_team_id
WHERE f.game_id = rg.game_id;
