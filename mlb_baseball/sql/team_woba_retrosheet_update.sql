-- Two corrections versus this file's original shape (both found by direct
-- audit alongside issue #9 item 6, same bug class as
-- team_rate_retrosheet_update.sql's db97d96 fix):
--
-- 1. Every event_cd FILTER is gated on `bat_event_fl = 'T'`, matching
--    team_starter_retrosheet_update.sql / team_bullpen_retrosheet_update.sql
--    (ADR-034). This file predates ADR-034's finding (the deGrom-2018
--    reconciliation proving the guard is required, not optional) and had
--    the same gap as team_rate_retrosheet_update.sql did before db97d96 --
--    tracked as issue #9 item 6.
-- 2. The rolling window orders by `game_date, game_number NULLS LAST,
--    game_id`, not `game_date, game_id` alone -- matching the base
--    family's own window (game_feature_rebuild.sql) and
--    team_rate_retrosheet_update.sql's own db97d96 fix. Found by direct
--    audit of this file (same team-partitioned window shape as
--    team_rate's pre-fix bug); not separately named in issue #9's text,
--    but the identical point-in-time-safety gap: a doubleheader loaded
--    "second game first" would leak the later game's stats into the
--    earlier game's "entering" value and vice versa.
WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.game_number, g.retro_game_id,
        g.home_team_id, g.away_team_id
    FROM core.game g
    WHERE g.game_type = 'regular'
),
team_game_stats AS (
    SELECT
        rg.game_id, rg.season, rg.game_date, rg.game_number,
        CASE WHEN re.bat_home_id = '1' THEN rg.home_team_id ELSE rg.away_team_id END AS team_id,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '14') AS ubb,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '16') AS hbp,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '20') AS b1,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '21') AS b2,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '22') AS b3,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '23') AS hr,
        count(*) FILTER (WHERE re.ab_fl = 'T') AS ab,
        count(*) FILTER (WHERE re.sf_fl = 'T') AS sf
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    GROUP BY rg.game_id, rg.season, rg.game_date, rg.game_number,
        CASE WHEN re.bat_home_id = '1' THEN rg.home_team_id ELSE rg.away_team_id END
),
rolling AS (
    SELECT game_id, team_id,
        SUM(ubb) OVER w AS ubb_sum, SUM(hbp) OVER w AS hbp_sum,
        SUM(b1) OVER w AS b1_sum, SUM(b2) OVER w AS b2_sum,
        SUM(b3) OVER w AS b3_sum, SUM(hr) OVER w AS hr_sum,
        SUM(ab) OVER w AS ab_sum, SUM(sf) OVER w AS sf_sum
    FROM team_game_stats
    WINDOW w AS (
        PARTITION BY team_id, season ORDER BY game_date, game_number NULLS LAST, game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),
woba AS (
    SELECT game_id, team_id,
        CASE WHEN (ab_sum + ubb_sum + sf_sum + hbp_sum) > 0 THEN
            (%(w_ubb)s * ubb_sum + %(w_hbp)s * hbp_sum + %(w_1b)s * b1_sum
                + %(w_2b)s * b2_sum + %(w_3b)s * b3_sum + %(w_hr)s * hr_sum)
            / (ab_sum + ubb_sum + sf_sum + hbp_sum)
        END AS value
    FROM rolling
)
UPDATE gold.game_feature f
SET home_woba = hw.value, away_woba = aw.value
FROM regular_games rg
LEFT JOIN woba hw ON hw.game_id = rg.game_id AND hw.team_id = rg.home_team_id
LEFT JOIN woba aw ON aw.game_id = rg.game_id AND aw.team_id = rg.away_team_id
WHERE f.game_id = rg.game_id
