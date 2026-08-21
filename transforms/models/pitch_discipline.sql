MODEL (
  name gold.pitch_discipline,
  kind INCREMENTAL_BY_TIME_RANGE (
    time_column game_date
  ),
  start '2021-01-01',
  cron '@monthly',
  grain (game_id, pitcher_retro_id),
  description '
    Point-in-time entering plate discipline and pitch sequence rates for
    pitchers from raw.retrosheet_event.pitch_seq_tx (PIT-07). Computes
    entering CSW% (Called Strike + Whiff %), Whiff%, and First-Pitch Strike%
    over expanding season-to-date windows strictly before the target game.
  '
);

WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.game_number, g.retro_game_id
    FROM core.game g
    WHERE g.game_type = 'regular'
),
clean_events AS (
    SELECT
        rg.game_id,
        rg.season,
        rg.game_date,
        rg.game_number,
        re.resp_pit_id AS pitcher_retro_id,
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
rolling AS (
    SELECT
        game_id,
        season,
        game_date,
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
)
SELECT
    game_id,
    pitcher_retro_id,
    season,
    game_date,
    CASE WHEN pitches_sum >= 20 THEN csw_sum::numeric / pitches_sum END AS csw_pct,
    CASE WHEN swings_sum >= 10 THEN whiffs_sum::numeric / swings_sum END AS whiff_pct,
    CASE WHEN pa_sum >= 5 THEN fstrikes_sum::numeric / pa_sum END AS fstrike_pct
FROM rolling
WHERE game_date BETWEEN @start_ds AND @end_ds;
