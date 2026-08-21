-- Computes entering-game batted-ball profile rates from raw.retrosheet_event
-- for starting pitchers, bullpens, and offensive lineups.
-- Zero lookahead leakage: strictly ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
-- within the same season, ordered by (game_date, game_number, game_id).

WITH event_parsed AS (
    SELECT
        re.game_id,
        re.bat_home_id,
        re.resp_pit_id,
        re.resp_pit_start_fl,
        re.battedball_cd,
        re.event_cd,
        re.h_cd,
        CASE WHEN re.battedball_cd = 'G' THEN 1 ELSE 0 END AS is_gb,
        CASE
            WHEN re.battedball_cd = 'F' THEN 1
            WHEN (re.event_cd = '23' OR re.h_cd = '4') AND (re.battedball_cd IS NULL OR re.battedball_cd = '') THEN 1
            ELSE 0
        END AS is_fb,
        CASE WHEN re.battedball_cd = 'L' THEN 1 ELSE 0 END AS is_ld,
        CASE WHEN re.battedball_cd = 'P' THEN 1 ELSE 0 END AS is_pu,
        CASE WHEN re.event_cd = '23' OR re.h_cd = '4' THEN 1 ELSE 0 END AS is_hr
    FROM raw.retrosheet_event re
),

event_classified AS (
    SELECT
        ep.*,
        CASE WHEN (ep.is_gb = 1 OR ep.is_fb = 1 OR ep.is_ld = 1 OR ep.is_pu = 1) THEN 1 ELSE 0 END AS is_bbe
    FROM event_parsed ep
),

games AS (
    SELECT
        g.id AS game_id,
        g.retro_game_id,
        g.season,
        g.game_date,
        g.game_number,
        g.home_team_id,
        g.away_team_id,
        f.home_starter_id,
        f.away_starter_id,
        hsp.retro_id AS home_starter_retro_id,
        asp.retro_id AS away_starter_retro_id
    FROM core.game g
    JOIN gold.game_feature f ON f.game_id = g.id
    LEFT JOIN core.player hsp ON hsp.id = f.home_starter_id
    LEFT JOIN core.player asp ON asp.id = f.away_starter_id
),

-- 1. Starter game-level aggregates
starter_game_agg AS (
    SELECT
        g.game_id,
        g.season,
        g.game_date,
        g.game_number,
        ec.resp_pit_id,
        SUM(ec.is_gb) AS gb_cnt,
        SUM(ec.is_fb) AS fb_cnt,
        SUM(ec.is_ld) AS ld_cnt,
        SUM(ec.is_pu) AS pu_cnt,
        SUM(ec.is_bbe) AS bbe_cnt,
        SUM(ec.is_hr) AS hr_cnt
    FROM event_classified ec
    JOIN games g ON g.retro_game_id = ec.game_id
    WHERE ec.resp_pit_start_fl = 'T'
      AND ec.resp_pit_id IS NOT NULL
      AND ec.resp_pit_id != ''
    GROUP BY g.game_id, g.season, g.game_date, g.game_number, ec.resp_pit_id
),

starter_rolling AS (
    SELECT
        game_id,
        resp_pit_id,
        SUM(gb_cnt) OVER w AS prior_gb,
        SUM(fb_cnt) OVER w AS prior_fb,
        SUM(ld_cnt) OVER w AS prior_ld,
        SUM(pu_cnt) OVER w AS prior_pu,
        SUM(bbe_cnt) OVER w AS prior_bbe,
        SUM(hr_cnt) OVER w AS prior_hr
    FROM starter_game_agg
    WINDOW w AS (
        PARTITION BY resp_pit_id, season
        ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),

starter_rates AS (
    SELECT
        game_id,
        resp_pit_id,
        CASE
            WHEN prior_bbe >= %(min_starter_bbe)s THEN ROUND(prior_gb::numeric / prior_bbe, 4)
            ELSE NULL
        END AS gb_pct,
        CASE
            WHEN prior_bbe >= %(min_starter_bbe)s THEN ROUND(prior_fb::numeric / prior_bbe, 4)
            ELSE NULL
        END AS fb_pct,
        CASE
            WHEN prior_bbe >= %(min_starter_bbe)s THEN ROUND(prior_ld::numeric / prior_bbe, 4)
            ELSE NULL
        END AS ld_pct,
        CASE
            WHEN prior_fb >= %(min_starter_fb)s THEN ROUND(prior_hr::numeric / prior_fb, 4)
            ELSE NULL
        END AS hr_per_fb
    FROM starter_rolling
),

-- 2. Bullpen game-level aggregates
bullpen_game_agg AS (
    SELECT
        g.game_id,
        g.season,
        g.game_date,
        g.game_number,
        CASE WHEN ec.bat_home_id = '0' THEN g.home_team_id ELSE g.away_team_id END AS team_id,
        SUM(ec.is_gb) AS gb_cnt,
        SUM(ec.is_fb) AS fb_cnt,
        SUM(ec.is_ld) AS ld_cnt,
        SUM(ec.is_pu) AS pu_cnt,
        SUM(ec.is_bbe) AS bbe_cnt,
        SUM(ec.is_hr) AS hr_cnt
    FROM event_classified ec
    JOIN games g ON g.retro_game_id = ec.game_id
    WHERE ec.resp_pit_start_fl = 'F'
    GROUP BY g.game_id, g.season, g.game_date, g.game_number,
             CASE WHEN ec.bat_home_id = '0' THEN g.home_team_id ELSE g.away_team_id END
),

bullpen_rolling AS (
    SELECT
        game_id,
        team_id,
        SUM(gb_cnt) OVER w AS prior_gb,
        SUM(fb_cnt) OVER w AS prior_fb,
        SUM(ld_cnt) OVER w AS prior_ld,
        SUM(pu_cnt) OVER w AS prior_pu,
        SUM(bbe_cnt) OVER w AS prior_bbe,
        SUM(hr_cnt) OVER w AS prior_hr
    FROM bullpen_game_agg
    WINDOW w AS (
        PARTITION BY team_id, season
        ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),

bullpen_rates AS (
    SELECT
        game_id,
        team_id,
        CASE
            WHEN prior_bbe >= %(min_bullpen_bbe)s THEN ROUND(prior_gb::numeric / prior_bbe, 4)
            ELSE NULL
        END AS gb_pct,
        CASE
            WHEN prior_bbe >= %(min_bullpen_bbe)s THEN ROUND(prior_fb::numeric / prior_bbe, 4)
            ELSE NULL
        END AS fb_pct,
        CASE
            WHEN prior_fb >= %(min_bullpen_fb)s THEN ROUND(prior_hr::numeric / prior_fb, 4)
            ELSE NULL
        END AS hr_per_fb
    FROM bullpen_rolling
),

-- 3. Team Batting game-level aggregates
batting_game_agg AS (
    SELECT
        g.game_id,
        g.season,
        g.game_date,
        g.game_number,
        CASE WHEN ec.bat_home_id = '1' THEN g.home_team_id ELSE g.away_team_id END AS team_id,
        SUM(ec.is_gb) AS gb_cnt,
        SUM(ec.is_fb) AS fb_cnt,
        SUM(ec.is_ld) AS ld_cnt,
        SUM(ec.is_pu) AS pu_cnt,
        SUM(ec.is_bbe) AS bbe_cnt,
        SUM(ec.is_hr) AS hr_cnt
    FROM event_classified ec
    JOIN games g ON g.retro_game_id = ec.game_id
    GROUP BY g.game_id, g.season, g.game_date, g.game_number,
             CASE WHEN ec.bat_home_id = '1' THEN g.home_team_id ELSE g.away_team_id END
),

batting_rolling AS (
    SELECT
        game_id,
        team_id,
        SUM(gb_cnt) OVER w AS prior_gb,
        SUM(fb_cnt) OVER w AS prior_fb,
        SUM(ld_cnt) OVER w AS prior_ld,
        SUM(pu_cnt) OVER w AS prior_pu,
        SUM(bbe_cnt) OVER w AS prior_bbe,
        SUM(hr_cnt) OVER w AS prior_hr
    FROM batting_game_agg
    WINDOW w AS (
        PARTITION BY team_id, season
        ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),

batting_rates AS (
    SELECT
        game_id,
        team_id,
        CASE
            WHEN prior_bbe >= %(min_batting_bbe)s THEN ROUND(prior_gb::numeric / prior_bbe, 4)
            ELSE NULL
        END AS gb_pct,
        CASE
            WHEN prior_bbe >= %(min_batting_bbe)s THEN ROUND(prior_fb::numeric / prior_bbe, 4)
            ELSE NULL
        END AS fb_pct,
        CASE
            WHEN prior_bbe >= %(min_batting_bbe)s THEN ROUND(prior_ld::numeric / prior_bbe, 4)
            ELSE NULL
        END AS ld_pct,
        CASE
            WHEN prior_fb >= %(min_batting_fb)s THEN ROUND(prior_hr::numeric / prior_fb, 4)
            ELSE NULL
        END AS hr_per_fb
    FROM batting_rolling
)

UPDATE gold.game_feature f
SET
    home_starter_gb_pct = hsr.gb_pct,
    home_starter_fb_pct = hsr.fb_pct,
    home_starter_ld_pct = hsr.ld_pct,
    home_starter_hr_per_fb = hsr.hr_per_fb,
    away_starter_gb_pct = asr.gb_pct,
    away_starter_fb_pct = asr.fb_pct,
    away_starter_ld_pct = asr.ld_pct,
    away_starter_hr_per_fb = asr.hr_per_fb,
    home_bullpen_gb_pct = hbr.gb_pct,
    home_bullpen_fb_pct = hbr.fb_pct,
    home_bullpen_hr_per_fb = hbr.hr_per_fb,
    away_bullpen_gb_pct = abr.gb_pct,
    away_bullpen_fb_pct = abr.fb_pct,
    away_bullpen_hr_per_fb = abr.hr_per_fb,
    home_batting_gb_pct = htr.gb_pct,
    home_batting_fb_pct = htr.fb_pct,
    home_batting_ld_pct = htr.ld_pct,
    home_batting_hr_per_fb = htr.hr_per_fb,
    away_batting_gb_pct = atr.gb_pct,
    away_batting_fb_pct = atr.fb_pct,
    away_batting_ld_pct = atr.ld_pct,
    away_batting_hr_per_fb = atr.hr_per_fb
FROM games g
LEFT JOIN starter_rates hsr ON hsr.game_id = g.game_id AND hsr.resp_pit_id = g.home_starter_retro_id
LEFT JOIN starter_rates asr ON asr.game_id = g.game_id AND asr.resp_pit_id = g.away_starter_retro_id
LEFT JOIN bullpen_rates hbr ON hbr.game_id = g.game_id AND hbr.team_id = g.home_team_id
LEFT JOIN bullpen_rates abr ON abr.game_id = g.game_id AND abr.team_id = g.away_team_id
LEFT JOIN batting_rates htr ON htr.game_id = g.game_id AND htr.team_id = g.home_team_id
LEFT JOIN batting_rates atr ON atr.game_id = g.game_id AND atr.team_id = g.away_team_id
WHERE f.game_id = g.game_id;
