MODEL (
    name gold.statcast_expected,
    kind FULL,
    cron '@daily',
    grain [game_id]
);

@DEF(min_starter_bip, 5);
@DEF(min_starter_ab, 10);
@DEF(min_starter_pa, 10);
@DEF(min_bullpen_bip, 5);
@DEF(min_bullpen_ab, 10);
@DEF(min_bullpen_pa, 10);
@DEF(min_batting_bip, 5);
@DEF(min_batting_ab, 10);
@DEF(min_batting_pa, 10);

WITH regular_games AS (
    SELECT
        g.id AS game_id,
        g.retro_game_id,
        g.season,
        g.game_date,
        g.game_number,
        ht.retro_team_id AS home_retro_id,
        at.retro_team_id AS away_retro_id,
        hp.retro_id AS home_starter_retro_id,
        ap.retro_id AS away_starter_retro_id
    FROM core.game g
    JOIN core.team ht ON ht.id = g.home_team_id
    JOIN core.team at ON at.id = g.away_team_id
    JOIN gold.game_feature f ON f.game_id = g.id
    LEFT JOIN core.player hp ON hp.id = f.home_starter_id
    LEFT JOIN core.player ap ON ap.id = f.away_starter_id
    WHERE lower(g.game_type) = 'regular'
),

event_parsed AS (
    SELECT
        re.game_id,
        re.inn_ct,
        re.bat_home_id,
        re.resp_pit_id,
        re.resp_pit_start_fl,
        re.event_id,
        re.event_cd,
        re.battedball_cd,
        re.h_cd,
        CASE
            WHEN re.battedball_cd IN ('G', 'F', 'L', 'P')
              OR ((re.event_cd = '23' OR re.h_cd = '4') AND (re.battedball_cd IS NULL OR re.battedball_cd = ''))
            THEN 1 ELSE 0
        END AS is_bip,
        CASE
            WHEN re.battedball_cd = 'L' OR re.event_cd = '23' OR re.h_cd IN ('2', '3', '4')
            THEN 1 ELSE 0
        END AS is_hard_hit,
        CASE
            WHEN (re.battedball_cd = 'L' AND re.event_cd IN ('21', '22', '23')) OR re.event_cd = '23' OR re.h_cd = '4'
            THEN 1 ELSE 0
        END AS is_barrel,
        CASE
            WHEN re.event_cd = '23' OR re.h_cd = '4' THEN 1.000
            WHEN re.battedball_cd = 'L' THEN 0.685
            WHEN re.battedball_cd = 'F' THEN 0.210
            WHEN re.battedball_cd = 'G' THEN 0.235
            WHEN re.battedball_cd = 'P' THEN 0.020
            ELSE 0.000
        END AS xba_contact,
        CASE
            WHEN re.event_cd = '23' OR re.h_cd = '4' THEN 4.000
            WHEN re.battedball_cd = 'L' THEN 0.880
            WHEN re.battedball_cd = 'F' THEN 0.560
            WHEN re.battedball_cd = 'G' THEN 0.260
            WHEN re.battedball_cd = 'P' THEN 0.020
            ELSE 0.000
        END AS xslg_contact,
        CASE
            WHEN re.event_cd = '23' OR re.h_cd = '4' THEN 2.100
            WHEN re.battedball_cd = 'L' THEN 0.650
            WHEN re.battedball_cd = 'F' THEN 0.320
            WHEN re.battedball_cd = 'G' THEN 0.220
            WHEN re.battedball_cd = 'P' THEN 0.020
            ELSE 0.000
        END AS xwoba_contact,
        CASE
            WHEN re.event_cd = '3'
              OR re.battedball_cd IN ('G', 'F', 'L', 'P')
              OR ((re.event_cd = '23' OR re.h_cd = '4') AND (re.battedball_cd IS NULL OR re.battedball_cd = ''))
            THEN 1 ELSE 0
        END AS is_ab,
        CASE WHEN re.event_cd IN ('14', '15') THEN 1 ELSE 0 END AS is_bb,
        CASE WHEN re.event_cd = '16' THEN 1 ELSE 0 END AS is_hbp
    FROM raw.retrosheet_event re
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = re.game_id AND lower(gi.gametype) = 'regular'
    WHERE re.bat_event_fl = 'T'
),

starter_game_agg AS (
    SELECT
        g.game_id,
        g.season,
        g.game_date,
        g.game_number,
        ep.resp_pit_id,
        COUNT(*) AS pa_cnt,
        SUM(ep.is_ab) AS ab_cnt,
        SUM(ep.is_bip) AS bip_cnt,
        SUM(ep.is_hard_hit) AS hard_hit_cnt,
        SUM(ep.is_barrel) AS barrel_cnt,
        SUM(ep.xba_contact) AS xba_sum,
        SUM(ep.xslg_contact) AS xslg_sum,
        SUM(ep.xwoba_contact) AS xwoba_contact_sum,
        SUM(ep.is_bb) AS bb_cnt,
        SUM(ep.is_hbp) AS hbp_cnt
    FROM regular_games g
    JOIN event_parsed ep ON ep.game_id = g.retro_game_id
    WHERE ep.resp_pit_start_fl = 'T'
      AND ep.resp_pit_id IS NOT NULL AND ep.resp_pit_id != ''
    GROUP BY g.game_id, g.season, g.game_date, g.game_number, ep.resp_pit_id
),

starter_rolling AS (
    SELECT
        game_id,
        resp_pit_id,
        SUM(pa_cnt) OVER w AS prior_pa,
        SUM(ab_cnt) OVER w AS prior_ab,
        SUM(bip_cnt) OVER w AS prior_bip,
        SUM(hard_hit_cnt) OVER w AS prior_hard_hit,
        SUM(barrel_cnt) OVER w AS prior_barrel,
        SUM(xba_sum) OVER w AS prior_xba_sum,
        SUM(xslg_sum) OVER w AS prior_xslg_sum,
        SUM(xwoba_contact_sum) OVER w AS prior_xwoba_contact_sum,
        SUM(bb_cnt) OVER w AS prior_bb,
        SUM(hbp_cnt) OVER w AS prior_hbp
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
            WHEN prior_bip >= @min_starter_bip THEN ROUND(prior_hard_hit::numeric / prior_bip, 4)
            ELSE NULL
        END AS starter_hard_hit_pct,
        CASE
            WHEN prior_bip >= @min_starter_bip THEN ROUND(prior_barrel::numeric / prior_bip, 4)
            ELSE NULL
        END AS starter_barrel_pct,
        CASE
            WHEN prior_ab >= @min_starter_ab THEN ROUND(prior_xba_sum::numeric / prior_ab, 4)
            ELSE NULL
        END AS starter_xba,
        CASE
            WHEN prior_ab >= @min_starter_ab THEN ROUND(prior_xslg_sum::numeric / prior_ab, 4)
            ELSE NULL
        END AS starter_xslg,
        CASE
            WHEN prior_pa >= @min_starter_pa THEN
                ROUND((prior_xwoba_contact_sum + 0.69 * prior_bb + 0.72 * prior_hbp)::numeric / prior_pa, 4)
            ELSE NULL
        END AS starter_xwoba
    FROM starter_rolling
),

bullpen_game_agg AS (
    SELECT
        g.game_id,
        g.season,
        g.game_date,
        g.game_number,
        CASE WHEN ep.bat_home_id = '1' THEN g.away_retro_id ELSE g.home_retro_id END AS pit_team_retro_id,
        COUNT(*) AS pa_cnt,
        SUM(ep.is_ab) AS ab_cnt,
        SUM(ep.is_bip) AS bip_cnt,
        SUM(ep.is_hard_hit) AS hard_hit_cnt,
        SUM(ep.is_barrel) AS barrel_cnt,
        SUM(ep.xba_contact) AS xba_sum,
        SUM(ep.xslg_contact) AS xslg_sum,
        SUM(ep.xwoba_contact) AS xwoba_contact_sum,
        SUM(ep.is_bb) AS bb_cnt,
        SUM(ep.is_hbp) AS hbp_cnt
    FROM regular_games g
    JOIN event_parsed ep ON ep.game_id = g.retro_game_id
    WHERE ep.resp_pit_start_fl = 'F'
    GROUP BY g.game_id, g.season, g.game_date, g.game_number,
             CASE WHEN ep.bat_home_id = '1' THEN g.away_retro_id ELSE g.home_retro_id END
),

bullpen_rolling AS (
    SELECT
        game_id,
        pit_team_retro_id,
        SUM(pa_cnt) OVER w AS prior_pa,
        SUM(ab_cnt) OVER w AS prior_ab,
        SUM(bip_cnt) OVER w AS prior_bip,
        SUM(hard_hit_cnt) OVER w AS prior_hard_hit,
        SUM(barrel_cnt) OVER w AS prior_barrel,
        SUM(xba_sum) OVER w AS prior_xba_sum,
        SUM(xslg_sum) OVER w AS prior_xslg_sum,
        SUM(xwoba_contact_sum) OVER w AS prior_xwoba_contact_sum,
        SUM(bb_cnt) OVER w AS prior_bb,
        SUM(hbp_cnt) OVER w AS prior_hbp
    FROM bullpen_game_agg
    WINDOW w AS (
        PARTITION BY pit_team_retro_id, season
        ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),

bullpen_rates AS (
    SELECT
        game_id,
        pit_team_retro_id,
        CASE
            WHEN prior_bip >= @min_bullpen_bip THEN ROUND(prior_hard_hit::numeric / prior_bip, 4)
            ELSE NULL
        END AS bullpen_hard_hit_pct,
        CASE
            WHEN prior_bip >= @min_bullpen_bip THEN ROUND(prior_barrel::numeric / prior_bip, 4)
            ELSE NULL
        END AS bullpen_barrel_pct,
        CASE
            WHEN prior_ab >= @min_bullpen_ab THEN ROUND(prior_xba_sum::numeric / prior_ab, 4)
            ELSE NULL
        END AS bullpen_xba,
        CASE
            WHEN prior_ab >= @min_bullpen_ab THEN ROUND(prior_xslg_sum::numeric / prior_ab, 4)
            ELSE NULL
        END AS bullpen_xslg,
        CASE
            WHEN prior_pa >= @min_bullpen_pa THEN
                ROUND((prior_xwoba_contact_sum + 0.69 * prior_bb + 0.72 * prior_hbp)::numeric / prior_pa, 4)
            ELSE NULL
        END AS bullpen_xwoba
    FROM bullpen_rolling
),

batting_game_agg AS (
    SELECT
        g.game_id,
        g.season,
        g.game_date,
        g.game_number,
        CASE WHEN ep.bat_home_id = '1' THEN g.home_retro_id ELSE g.away_retro_id END AS bat_team_retro_id,
        COUNT(*) AS pa_cnt,
        SUM(ep.is_ab) AS ab_cnt,
        SUM(ep.is_bip) AS bip_cnt,
        SUM(ep.is_hard_hit) AS hard_hit_cnt,
        SUM(ep.is_barrel) AS barrel_cnt,
        SUM(ep.xba_contact) AS xba_sum,
        SUM(ep.xslg_contact) AS xslg_sum,
        SUM(ep.xwoba_contact) AS xwoba_contact_sum,
        SUM(ep.is_bb) AS bb_cnt,
        SUM(ep.is_hbp) AS hbp_cnt
    FROM regular_games g
    JOIN event_parsed ep ON ep.game_id = g.retro_game_id
    GROUP BY g.game_id, g.season, g.game_date, g.game_number,
             CASE WHEN ep.bat_home_id = '1' THEN g.home_retro_id ELSE g.away_retro_id END
),

batting_rolling AS (
    SELECT
        game_id,
        bat_team_retro_id,
        SUM(pa_cnt) OVER w AS prior_pa,
        SUM(ab_cnt) OVER w AS prior_ab,
        SUM(bip_cnt) OVER w AS prior_bip,
        SUM(hard_hit_cnt) OVER w AS prior_hard_hit,
        SUM(barrel_cnt) OVER w AS prior_barrel,
        SUM(xba_sum) OVER w AS prior_xba_sum,
        SUM(xslg_sum) OVER w AS prior_xslg_sum,
        SUM(xwoba_contact_sum) OVER w AS prior_xwoba_contact_sum,
        SUM(bb_cnt) OVER w AS prior_bb,
        SUM(hbp_cnt) OVER w AS prior_hbp
    FROM batting_game_agg
    WINDOW w AS (
        PARTITION BY bat_team_retro_id, season
        ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),

batting_rates AS (
    SELECT
        game_id,
        bat_team_retro_id,
        CASE
            WHEN prior_bip >= @min_batting_bip THEN ROUND(prior_hard_hit::numeric / prior_bip, 4)
            ELSE NULL
        END AS offense_hard_hit_pct,
        CASE
            WHEN prior_bip >= @min_batting_bip THEN ROUND(prior_barrel::numeric / prior_bip, 4)
            ELSE NULL
        END AS offense_barrel_pct,
        CASE
            WHEN prior_ab >= @min_batting_ab THEN ROUND(prior_xba_sum::numeric / prior_ab, 4)
            ELSE NULL
        END AS offense_xba,
        CASE
            WHEN prior_ab >= @min_batting_ab THEN ROUND(prior_xslg_sum::numeric / prior_ab, 4)
            ELSE NULL
        END AS offense_xslg,
        CASE
            WHEN prior_pa >= @min_batting_pa THEN
                ROUND((prior_xwoba_contact_sum + 0.69 * prior_bb + 0.72 * prior_hbp)::numeric / prior_pa, 4)
            ELSE NULL
        END AS offense_xwoba
    FROM batting_rolling
)

SELECT
    g.game_id,
    h_sr.starter_hard_hit_pct AS home_starter_hard_hit_pct,
    a_sr.starter_hard_hit_pct AS away_starter_hard_hit_pct,
    h_sr.starter_barrel_pct AS home_starter_barrel_pct,
    a_sr.starter_barrel_pct AS away_starter_barrel_pct,
    h_sr.starter_xwoba AS home_starter_xwoba,
    a_sr.starter_xwoba AS away_starter_xwoba,
    h_sr.starter_xba AS home_starter_xba,
    a_sr.starter_xba AS away_starter_xba,
    h_sr.starter_xslg AS home_starter_xslg,
    a_sr.starter_xslg AS away_starter_xslg,

    h_br.bullpen_hard_hit_pct AS home_bullpen_hard_hit_pct,
    a_br.bullpen_hard_hit_pct AS away_bullpen_hard_hit_pct,
    h_br.bullpen_barrel_pct AS home_bullpen_barrel_pct,
    a_br.bullpen_barrel_pct AS away_bullpen_barrel_pct,
    h_br.bullpen_xwoba AS home_bullpen_xwoba,
    a_br.bullpen_xwoba AS away_bullpen_xwoba,
    h_br.bullpen_xba AS home_bullpen_xba,
    a_br.bullpen_xba AS away_bullpen_xba,
    h_br.bullpen_xslg AS home_bullpen_xslg,
    a_br.bullpen_xslg AS away_bullpen_xslg,

    h_otr.offense_hard_hit_pct AS home_offense_hard_hit_pct,
    a_otr.offense_hard_hit_pct AS away_offense_hard_hit_pct,
    h_otr.offense_barrel_pct AS home_offense_barrel_pct,
    a_otr.offense_barrel_pct AS away_offense_barrel_pct,
    h_otr.offense_xwoba AS home_offense_xwoba,
    a_otr.offense_xwoba AS away_offense_xwoba,
    h_otr.offense_xba AS home_offense_xba,
    a_otr.offense_xba AS away_offense_xba,
    h_otr.offense_xslg AS home_offense_xslg,
    a_otr.offense_xslg AS away_offense_xslg
FROM regular_games g
LEFT JOIN starter_rates h_sr ON h_sr.game_id = g.game_id AND h_sr.resp_pit_id = g.home_starter_retro_id
LEFT JOIN starter_rates a_sr ON a_sr.game_id = g.game_id AND a_sr.resp_pit_id = g.away_starter_retro_id
LEFT JOIN bullpen_rates h_br ON h_br.game_id = g.game_id AND h_br.pit_team_retro_id = g.home_retro_id
LEFT JOIN bullpen_rates a_br ON a_br.game_id = g.game_id AND a_br.pit_team_retro_id = g.away_retro_id
LEFT JOIN batting_rates h_otr ON h_otr.game_id = g.game_id AND h_otr.bat_team_retro_id = g.home_retro_id
LEFT JOIN batting_rates a_otr ON a_otr.game_id = g.game_id AND a_otr.bat_team_retro_id = g.away_retro_id;
