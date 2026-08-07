WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.retro_game_id
    FROM core.game g WHERE g.game_type = 'regular'
),
-- Aggregate both sides before the rolling frame: league wOBA entering one
-- game must be identical for its home and away rows.
game_stats AS (
    SELECT rg.game_id, rg.season, rg.game_date,
        count(*) FILTER (WHERE re.event_cd = '14') AS ubb,
        count(*) FILTER (WHERE re.event_cd = '16') AS hbp,
        count(*) FILTER (WHERE re.event_cd = '20') AS b1,
        count(*) FILTER (WHERE re.event_cd = '21') AS b2,
        count(*) FILTER (WHERE re.event_cd = '22') AS b3,
        count(*) FILTER (WHERE re.event_cd = '23') AS hr,
        count(*) FILTER (WHERE re.ab_fl = 'T') AS ab,
        count(*) FILTER (WHERE re.sf_fl = 'T') AS sf
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    GROUP BY rg.game_id, rg.season, rg.game_date
),
league_rolling AS (
    SELECT game_id,
        SUM(ubb) OVER w AS ubb_sum, SUM(hbp) OVER w AS hbp_sum,
        SUM(b1) OVER w AS b1_sum, SUM(b2) OVER w AS b2_sum,
        SUM(b3) OVER w AS b3_sum, SUM(hr) OVER w AS hr_sum,
        SUM(ab) OVER w AS ab_sum, SUM(sf) OVER w AS sf_sum
    FROM game_stats
    WINDOW w AS (
        PARTITION BY season ORDER BY game_date, game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),
league_woba AS (
    SELECT game_id,
        CASE WHEN (ab_sum + ubb_sum + sf_sum + hbp_sum) > 0 THEN
            (%(w_ubb)s * ubb_sum + %(w_hbp)s * hbp_sum + %(w_1b)s * b1_sum
                + %(w_2b)s * b2_sum + %(w_3b)s * b3_sum + %(w_hr)s * hr_sum)
            / (ab_sum + ubb_sum + sf_sum + hbp_sum)
        END AS value
    FROM league_rolling
)
UPDATE gold.game_feature f
SET
    home_wrc_plus = CASE
        WHEN f.home_woba IS NOT NULL AND lw.value IS NOT NULL AND f.park_factor IS NOT NULL
        THEN (((f.home_woba - lw.value) / %(woba_scale)s) + 1) / (f.park_factor / 100.0) * 100
    END,
    away_wrc_plus = CASE
        WHEN f.away_woba IS NOT NULL AND lw.value IS NOT NULL AND f.park_factor IS NOT NULL
        THEN (((f.away_woba - lw.value) / %(woba_scale)s) + 1) / (f.park_factor / 100.0) * 100
    END
FROM league_woba lw
WHERE f.game_id = lw.game_id
