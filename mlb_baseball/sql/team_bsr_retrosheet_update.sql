-- Prior rolling team stolen-base run value (wSB), Tom Tango's linear-
-- weights formula (BSR-01, docs/FEATURE_ADMISSION_QUEUE.md, ADR-081):
--   wSB = SB*runSB + CS*runCS - lgwSB*(1B+BB+HBP-IBB)
--   lgwSB = (lgSB*runSB + lgCS*runCS) / (lg1B+lgBB+lgHBP-lgIBB)
-- runSB/runCS come in as query params (mlb_baseball/model/bsr.py::RUN_SB/
-- RUN_CS) -- established, cited constants (FanGraphs library page linked
-- in the admission queue row), not season-refit here.
--
-- "1B+BB+HBP-IBB" simplifies to "1B+UBB+HBP" (BB is UBB+IBB, so BB-IBB
-- cancels the IBB term exactly) -- this SQL uses that simplified form
-- directly, so IBB is never separately counted at all, at either the
-- team or league grain.
--
-- SB/CS counting is NOT gated on bat_event_fl='T' (unlike the 1B/BB/HBP
-- opportunity counts below, which follow team_rate_retrosheet_update.sql's
-- existing gate) -- confirmed against real production `mlb` data before
-- writing this: the large majority of real stolen-base attempts
-- (run1_sb_fl/run2_sb_fl/run3_sb_fl='T' rows) have bat_event_fl='F'
-- (e.g. a bare "SB2" row on a non-PA-ending pitch is not itself a plate
-- appearance), and gating on bat_event_fl='T' would silently drop most of
-- them. run1_sb_fl/run2_sb_fl/run3_sb_fl (and their _cs_fl twins) are
-- Chadwick cwevent's own per-runner advance flags -- checked directly
-- against event_cd/event_tx on real data and confirmed to also catch
-- attempts embedded as a secondary event on a different play's primary
-- event (e.g. "K+CS2(24)", primary event_cd=3/strikeout): using these
-- flags instead of primary event_cd IN ('4','6') catches 251,782 real SB
-- events versus 226,458 from primary event_cd alone (11%% more), and
-- 138,254 real CS events versus 113,100 (22%% more) -- a primary-event-
-- code-only count would materially undercount, especially CS.
--
-- League-wide entering context (lgwSB) uses date-level granularity, not
-- the team-level window's (game_date, game_number, game_id) row
-- granularity -- game_number isn't comparable across two different
-- teams' games on the same date, so the league aggregate rolls up to one
-- row per (season, game_date) and its own window excludes the entire
-- current date, not just strictly-prior rows. This is a stricter (more
-- point-in-time-safe) cutoff than the team-level window uses for a same-
-- team doubleheader nightcap, not a looser one.
--
-- MIN_ATTEMPTS (SB+CS entering-value gate) is a chosen, documented
-- sample-size floor (mlb_baseball/model/bsr.py), not a derived or cited
-- number -- same posture as team_rate.py's own MIN_PA/MIN_AB thresholds.

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
        count(*) FILTER (WHERE re.run1_sb_fl = 'T')
            + count(*) FILTER (WHERE re.run2_sb_fl = 'T')
            + count(*) FILTER (WHERE re.run3_sb_fl = 'T') AS sb,
        count(*) FILTER (WHERE re.run1_cs_fl = 'T')
            + count(*) FILTER (WHERE re.run2_cs_fl = 'T')
            + count(*) FILTER (WHERE re.run3_cs_fl = 'T') AS cs,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '20') AS b1,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '14') AS ubb,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '16') AS hbp
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    GROUP BY rg.game_id, rg.season, rg.game_date, rg.game_number,
        CASE WHEN re.bat_home_id = '1' THEN rg.home_team_id ELSE rg.away_team_id END
),
team_rolling AS (
    SELECT game_id, team_id, season, game_date,
        SUM(sb) OVER w AS sb_sum, SUM(cs) OVER w AS cs_sum,
        SUM(b1) OVER w AS b1_sum, SUM(ubb) OVER w AS ubb_sum, SUM(hbp) OVER w AS hbp_sum
    FROM team_game_stats
    WINDOW w AS (
        PARTITION BY team_id, season ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),
league_daily AS (
    SELECT season, game_date,
        SUM(sb) AS sb, SUM(cs) AS cs, SUM(b1) AS b1, SUM(ubb) AS ubb, SUM(hbp) AS hbp
    FROM team_game_stats
    GROUP BY season, game_date
),
league_rolling AS (
    SELECT season, game_date,
        SUM(sb) OVER w AS sb_sum, SUM(cs) OVER w AS cs_sum,
        SUM(b1) OVER w AS b1_sum, SUM(ubb) OVER w AS ubb_sum, SUM(hbp) OVER w AS hbp_sum
    FROM league_daily
    WINDOW w AS (
        PARTITION BY season ORDER BY game_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),
league_wsb AS (
    SELECT season, game_date,
        CASE WHEN (b1_sum + ubb_sum + hbp_sum) > 0 THEN
            (COALESCE(sb_sum, 0) * %(run_sb)s::numeric + COALESCE(cs_sum, 0) * %(run_cs)s::numeric)
                / (b1_sum + ubb_sum + hbp_sum)
        END AS lgwsb
    FROM league_rolling
),
computed AS (
    SELECT tr.game_id, tr.team_id, tr.sb_sum, tr.cs_sum,
        (COALESCE(tr.b1_sum, 0) + COALESCE(tr.ubb_sum, 0) + COALESCE(tr.hbp_sum, 0)) AS opp_sum,
        lg.lgwsb
    FROM team_rolling tr
    LEFT JOIN league_wsb lg ON lg.season = tr.season AND lg.game_date = tr.game_date
),
wsb AS (
    SELECT game_id, team_id, sb_sum, cs_sum,
        CASE WHEN COALESCE(sb_sum, 0) + COALESCE(cs_sum, 0) >= %(min_attempts)s AND lgwsb IS NOT NULL THEN
            COALESCE(sb_sum, 0) * %(run_sb)s::numeric + COALESCE(cs_sum, 0) * %(run_cs)s::numeric
                - lgwsb * opp_sum
        END AS wsb
    FROM computed
)
UPDATE gold.game_feature f
SET home_sb = wh.sb_sum, away_sb = wa.sb_sum,
    home_cs = wh.cs_sum, away_cs = wa.cs_sum,
    home_wsb = wh.wsb, away_wsb = wa.wsb
FROM regular_games rg
LEFT JOIN wsb wh ON wh.game_id = rg.game_id AND wh.team_id = rg.home_team_id
LEFT JOIN wsb wa ON wa.game_id = rg.game_id AND wa.team_id = rg.away_team_id
WHERE f.game_id = rg.game_id;
