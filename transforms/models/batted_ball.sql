MODEL (
  name gold.batted_ball,
  kind INCREMENTAL_BY_TIME_RANGE (
    time_column game_date
  ),
  start '2021-01-01',
  cron '@monthly',
  grain (game_id, pitcher_retro_id),
  description '
    Point-in-time entering batted-ball rates (GB%, FB%, LD%, HR/FB) for
    pitchers from raw.retrosheet_event (BAT-01, OFF-10). Computes entering
    ground ball, fly ball, line drive, and HR/FB rates over expanding
    season-to-date windows strictly before the target game.
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
        CASE WHEN re.battedball_cd = 'G' THEN 1 ELSE 0 END AS is_gb,
        CASE
            WHEN re.battedball_cd = 'F' THEN 1
            WHEN (re.event_cd = '23' OR re.h_cd = '4') AND (re.battedball_cd IS NULL OR re.battedball_cd = '') THEN 1
            ELSE 0
        END AS is_fb,
        CASE WHEN re.battedball_cd = 'L' THEN 1 ELSE 0 END AS is_ld,
        CASE WHEN re.battedball_cd = 'P' THEN 1 ELSE 0 END AS is_pu,
        CASE WHEN (re.battedball_cd IN ('G', 'F', 'L', 'P') OR re.event_cd = '23' OR re.h_cd = '4') THEN 1 ELSE 0 END AS is_bbe,
        CASE WHEN re.event_cd = '23' OR re.h_cd = '4' THEN 1 ELSE 0 END AS is_hr
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    WHERE re.resp_pit_id IS NOT NULL AND re.resp_pit_id != ''
),
pitcher_game_stats AS (
    SELECT
        game_id,
        season,
        game_date,
        game_number,
        pitcher_retro_id,
        SUM(is_gb) AS gb_cnt,
        SUM(is_fb) AS fb_cnt,
        SUM(is_ld) AS ld_cnt,
        SUM(is_pu) AS pu_cnt,
        SUM(is_bbe) AS bbe_cnt,
        SUM(is_hr) AS hr_cnt
    FROM clean_events
    GROUP BY game_id, season, game_date, game_number, pitcher_retro_id
),
rolling AS (
    SELECT
        game_id,
        season,
        game_date,
        game_number,
        pitcher_retro_id,
        SUM(gb_cnt) OVER w AS prior_gb,
        SUM(fb_cnt) OVER w AS prior_fb,
        SUM(ld_cnt) OVER w AS prior_ld,
        SUM(pu_cnt) OVER w AS prior_pu,
        SUM(bbe_cnt) OVER w AS prior_bbe,
        SUM(hr_cnt) OVER w AS prior_hr
    FROM pitcher_game_stats
    WINDOW w AS (
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
    CASE WHEN prior_bbe >= 30 THEN ROUND(prior_gb::numeric / prior_bbe, 4) ELSE NULL END AS gb_pct,
    CASE WHEN prior_bbe >= 30 THEN ROUND(prior_fb::numeric / prior_bbe, 4) ELSE NULL END AS fb_pct,
    CASE WHEN prior_bbe >= 30 THEN ROUND(prior_ld::numeric / prior_bbe, 4) ELSE NULL END AS ld_pct,
    CASE WHEN prior_fb >= 10 THEN ROUND(prior_hr::numeric / prior_fb, 4) ELSE NULL END AS hr_per_fb,
    prior_bbe AS bbe_sample,
    prior_fb AS fb_sample
FROM rolling
WHERE game_date BETWEEN @start_ds AND @end_ds;
