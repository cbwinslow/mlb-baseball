-- Rebuild gold.batting_game from raw.retrosheet_event (1910-2025).
--
-- Truncate-and-replace, transactional, idempotent (running twice produces
-- identical rows). Optional %(season)s bind scopes the rebuild to one season;
-- NULL rebuilds every season.
--
-- Event-flag handling matches sql/team_woba_retrosheet_update.sql exactly
-- (bat_event_fl / ab_fl / sf_fl / sh_fl for the batting-event gate; event_cd
-- 20-23 for hit type; ADR-034's finding that the bat_event_fl guard is
-- required, not optional). Building from core.play instead would diverge from
-- those already-tied-out numbers, because core.play carries none of these
-- flags (inventory 2026-09-01, section 4).
--
-- Retrosheet destination codes (bat_dest_id / run{1,2,3}_dest_id): 0 = out or
-- did not advance, 1/2/3 = ended on that base, 4/5/6 = scored. A player's runs
-- for the game = times their own PA ended 4+ plus times they were a baserunner
-- (base{1,2,3}_run_id) whose dest ended 4+ on a later PA.
--
-- Known limitations (left NULL/0 with a reason, never guessed):
--   * gidp uses (dp_fl = 'T' AND battedball_cd = 'G'); battedball_cd is sparse
--     before 1988, so gidp undercounts early seasons. GIDP was also not
--     consistently scored before the 1930s.
--   * 2026+ games (MLB Stats API play-by-play) are not covered here -- a
--     separate builder over raw.mlb_playbyplay follows.
--
-- The caller (report._build_batting_game) TRUNCATEs gold.batting_game first,
-- in the same transaction. This file is one parameterized statement so psycopg
-- can prepare it (a multi-statement string with a bind fails to prepare).

INSERT INTO gold.batting_game (
    game_id, player_id, team_id, season, game_date,
    pa, ab, r, h, b1, b2, b3, hr, tb, rbi, bb, ibb, hbp, sf, sh, so, gidp
)
WITH ev AS (
    SELECT
        g.id AS game_id,
        g.season,
        g.game_date,
        re.bat_id,
        CASE WHEN re.bat_home_id = '1' THEN g.home_team_id ELSE g.away_team_id END AS team_id,
        re.event_cd,
        re.bat_event_fl,
        re.ab_fl,
        re.sf_fl,
        re.sh_fl,
        re.dp_fl,
        re.battedball_cd,
        NULLIF(re.rbi_ct, '')::integer AS rbi_ct,
        NULLIF(re.bat_dest_id, '')::integer  AS bat_dest_id,
        NULLIF(re.run1_dest_id, '')::integer AS run1_dest_id,
        NULLIF(re.run2_dest_id, '')::integer AS run2_dest_id,
        NULLIF(re.run3_dest_id, '')::integer AS run3_dest_id,
        NULLIF(re.base1_run_id, '') AS base1_run_id,
        NULLIF(re.base2_run_id, '') AS base2_run_id,
        NULLIF(re.base3_run_id, '') AS base3_run_id
    FROM core.game g
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = g.retro_game_id
    JOIN raw.retrosheet_event re ON re.game_id = g.retro_game_id
    WHERE g.retro_game_id IS NOT NULL
      AND lower(g.game_type) = 'regular'   -- regular season only, matching the existing
                                    -- gold season tables and Baseball-Reference's
                                    -- convention; postseason/all-star is a follow-up.
      AND (%(season)s::integer IS NULL OR g.season = %(season)s::integer)
),
batting AS (
    SELECT
        game_id, season, game_date, bat_id, team_id,
        count(*) FILTER (WHERE bat_event_fl = 'T')                              AS pa,
        count(*) FILTER (WHERE ab_fl = 'T')                                     AS ab,
        count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd IN ('20','21','22','23')) AS h,
        count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd = '20')          AS b1,
        count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd = '21')          AS b2,
        count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd = '22')          AS b3,
        count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd = '23')          AS hr,
        coalesce(sum(rbi_ct), 0)                                                AS rbi,
        count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd IN ('14','15'))  AS bb,
        count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd = '15')          AS ibb,
        count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd = '16')          AS hbp,
        count(*) FILTER (WHERE sf_fl = 'T')                                     AS sf,
        count(*) FILTER (WHERE sh_fl = 'T')                                     AS sh,
        count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd = '3')           AS so,
        count(*) FILTER (WHERE dp_fl = 'T' AND battedball_cd = 'G')             AS gidp
    FROM ev
    WHERE bat_id IS NOT NULL AND bat_id <> ''
    GROUP BY game_id, season, game_date, bat_id, team_id
    -- One row per batter who actually came to the plate. A pure pinch-runner
    -- (PA = 0, maybe scored a run) is a baserunning-only appearance and
    -- belongs in a later gold.baserunning_game relation, not here.
    HAVING count(*) FILTER (WHERE bat_event_fl = 'T') > 0
),
runs AS (
    SELECT game_id, runner_id, count(*) AS r
    FROM (
        SELECT game_id, bat_id       AS runner_id FROM ev WHERE bat_dest_id  >= 4
        UNION ALL
        SELECT game_id, base1_run_id FROM ev WHERE run1_dest_id >= 4 AND base1_run_id IS NOT NULL
        UNION ALL
        SELECT game_id, base2_run_id FROM ev WHERE run2_dest_id >= 4 AND base2_run_id IS NOT NULL
        UNION ALL
        SELECT game_id, base3_run_id FROM ev WHERE run3_dest_id >= 4 AND base3_run_id IS NOT NULL
    ) s
    WHERE runner_id IS NOT NULL AND runner_id <> ''
    GROUP BY game_id, runner_id
)
SELECT
    b.game_id,
    p.id AS player_id,
    b.team_id,
    b.season,
    b.game_date,
    b.pa, b.ab, coalesce(r.r, 0) AS r, b.h, b.b1, b.b2, b.b3, b.hr,
    b.b1 + 2 * b.b2 + 3 * b.b3 + 4 * b.hr AS tb,
    b.rbi, b.bb, b.ibb, b.hbp, b.sf, b.sh, b.so, b.gidp
FROM batting b
JOIN core.player p ON p.retro_id = b.bat_id
LEFT JOIN runs r ON r.game_id = b.game_id AND r.runner_id = b.bat_id;
