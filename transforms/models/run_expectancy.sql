MODEL (
  name gold.run_expectancy,
  kind INCREMENTAL_BY_TIME_RANGE (
    time_column game_date
  ),
  start '2021-01-01',
  cron '@monthly',
  grain (game_id, pitcher_retro_id),
  description '
    Point-in-time entering average Leverage Index (LI) for pitchers
    from raw.retrosheet_event (ADR-090, Package 3). Computes entering
    average leverage over expanding season-to-date windows strictly
    before the target game.
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
        CASE
            WHEN re.outs_ct::integer = 0 THEN
                CASE
                    WHEN re.base1_run_id IS NOT NULL AND re.base2_run_id IS NOT NULL AND re.base3_run_id IS NOT NULL THEN 2.10
                    WHEN re.base2_run_id IS NOT NULL AND re.base3_run_id IS NOT NULL THEN 1.80
                    WHEN re.base1_run_id IS NOT NULL AND re.base3_run_id IS NOT NULL THEN 1.65
                    WHEN re.base1_run_id IS NOT NULL AND re.base2_run_id IS NOT NULL THEN 1.55
                    WHEN re.base3_run_id IS NOT NULL THEN 1.45
                    WHEN re.base2_run_id IS NOT NULL THEN 1.25
                    WHEN re.base1_run_id IS NOT NULL THEN 1.15
                    ELSE 0.85
                END
            WHEN re.outs_ct::integer = 1 THEN
                CASE
                    WHEN re.base1_run_id IS NOT NULL AND re.base2_run_id IS NOT NULL AND re.base3_run_id IS NOT NULL THEN 2.05
                    WHEN re.base2_run_id IS NOT NULL AND re.base3_run_id IS NOT NULL THEN 1.75
                    WHEN re.base1_run_id IS NOT NULL AND re.base3_run_id IS NOT NULL THEN 1.60
                    WHEN re.base1_run_id IS NOT NULL AND re.base2_run_id IS NOT NULL THEN 1.50
                    WHEN re.base3_run_id IS NOT NULL THEN 1.40
                    WHEN re.base2_run_id IS NOT NULL THEN 1.20
                    WHEN re.base1_run_id IS NOT NULL THEN 1.05
                    ELSE 0.70
                END
            ELSE
                CASE
                    WHEN re.base1_run_id IS NOT NULL AND re.base2_run_id IS NOT NULL AND re.base3_run_id IS NOT NULL THEN 1.90
                    WHEN re.base2_run_id IS NOT NULL AND re.base3_run_id IS NOT NULL THEN 1.60
                    WHEN re.base1_run_id IS NOT NULL AND re.base3_run_id IS NOT NULL THEN 1.45
                    WHEN re.base1_run_id IS NOT NULL AND re.base2_run_id IS NOT NULL THEN 1.35
                    WHEN re.base3_run_id IS NOT NULL THEN 1.25
                    WHEN re.base2_run_id IS NOT NULL THEN 1.05
                    WHEN re.base1_run_id IS NOT NULL THEN 0.85
                    ELSE 0.50
                END
        END AS leverage_index
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    WHERE re.resp_pit_id IS NOT NULL AND re.resp_pit_id != ''
      AND re.bat_event_fl = 'T'
),
pitcher_game_stats AS (
    SELECT
        game_id,
        season,
        game_date,
        game_number,
        pitcher_retro_id,
        COUNT(*) AS pa_cnt,
        SUM(leverage_index) AS li_sum
    FROM clean_events
    GROUP BY game_id, season, game_date, game_number, pitcher_retro_id
),
rolling AS (
    SELECT
        game_id,
        season,
        game_date,
        pitcher_retro_id,
        SUM(pa_cnt) OVER w AS prior_pa,
        SUM(li_sum) OVER w AS prior_li_sum
    FROM pitcher_game_stats
    WINDOW w AS (
        PARTITION BY pitcher_retro_id, season
        ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
)
SELECT
    game_id,
    season,
    game_date,
    pitcher_retro_id,
    prior_pa,
    CASE
        WHEN prior_pa >= 30 THEN ROUND((prior_li_sum / prior_pa)::numeric, 4)
        ELSE NULL
    END AS entering_avg_li
FROM rolling
WHERE game_date BETWEEN @start_date AND @end_date;
