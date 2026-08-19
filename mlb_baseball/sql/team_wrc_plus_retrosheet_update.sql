-- Two corrections versus this file's original shape (both found by direct
-- audit alongside issue #9 item 6, same bug class as
-- team_rate_retrosheet_update.sql's db97d96 fix) -- see
-- team_woba_retrosheet_update.sql's identical header comment for the full
-- explanation of both:
-- 1. Every event_cd FILTER is gated on `bat_event_fl = 'T'` (ADR-034).
-- 2. The rolling window orders by `game_date, home_team_id, away_team_id,
--    COALESCE(game_number, 0), game_id`, not `game_date, game_id` alone.
--    This file's window is season-wide (every game in the league, not one
--    team), so `game_number` alone is NOT a safe tiebreak here the way it
--    is in team_woba/team_rate/team_bullpen's team-partitioned windows:
--    game_number only orders two games of the SAME matchup's doubleheader
--    against each other, it carries no meaning between two DIFFERENT
--    matchups that happen to share a game_date (flagged independently by
--    three reviewers on the PR that introduced this fix, PR #25 -- a real
--    P1, not a nitpick: ordering league-wide by game_number alone would
--    put every date's doubleheader-game-1's ahead of every single game
--    and every doubleheader-game-2 that same date, regardless of actual
--    matchup or first-pitch time). home_team_id/away_team_id sort first
--    among same-date ties specifically so game_number only ever
--    disambiguates two rows that are already known to be the same
--    matchup's own doubleheader -- unrelated same-date games remain
--    ordered by team-pair (still not true chronology, since this dataset
--    has no usable first-pitch timestamp, but at least never pretends a
--    false doubleheader relationship between two different matchups).
--    COALESCE(game_number, 0), not `game_number NULLS LAST`: see
--    team_rate_retrosheet_update.sql's own comment (issue #28) -- confirmed
--    against real production `mlb` data that Retrosheet's raw `number`
--    field is genuinely empty for 10,020 games (all 1901-1909), which
--    `NULLS LAST` would sort after its true doubleheader partner
--    regardless of actual order. This file wasn't in issue #28's original
--    file list -- it was added later (issue #9 item 6), after that issue
--    was filed -- but has the identical window shape and the identical gap.
WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.game_number, g.retro_game_id,
        g.home_team_id, g.away_team_id
    FROM core.game g WHERE g.game_type = 'regular'
),
-- Aggregate both sides before the rolling frame: league wOBA entering one
-- game must be identical for its home and away rows.
game_stats AS (
    SELECT rg.game_id, rg.season, rg.game_date, rg.game_number,
        rg.home_team_id, rg.away_team_id,
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
    GROUP BY rg.game_id, rg.season, rg.game_date, rg.game_number, rg.home_team_id, rg.away_team_id
),
league_rolling AS (
    SELECT game_id,
        SUM(ubb) OVER w AS ubb_sum, SUM(hbp) OVER w AS hbp_sum,
        SUM(b1) OVER w AS b1_sum, SUM(b2) OVER w AS b2_sum,
        SUM(b3) OVER w AS b3_sum, SUM(hr) OVER w AS hr_sum,
        SUM(ab) OVER w AS ab_sum, SUM(sf) OVER w AS sf_sum
    FROM game_stats
    WINDOW w AS (
        PARTITION BY season
        ORDER BY game_date, home_team_id, away_team_id, COALESCE(game_number, 0), game_id
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
