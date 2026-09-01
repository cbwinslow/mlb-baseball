-- Rebuild gold.pitching_game from raw.retrosheet_event (1910-2025).
--
-- Truncate-and-replace (caller TRUNCATEs first, same transaction),
-- transactional, idempotent. Optional %(season)s bind scopes the rebuild.
--
-- Every play is charged to re.resp_pit_id -- Chadwick's docs (verified, see
-- DECISIONS.md's starter.py ADR) confirm this is the pitcher actually charged
-- for the play, correct across mid-at-bat substitutions. Batters faced, outs
-- (event_outs_ct), and the H/BB/K/HR/HBP line all group by resp_pit_id.
--
-- Runs are charged per runner: the batter-runner's run (bat_dest_id >= 4) to
-- re.resp_pit_id, and a runner-on-base's run (run{1,2,3}_dest_id >= 4) to
-- re.run{1,2,3}_resp_pit_id -- so an inherited runner's run lands on the
-- pitcher who allowed them to reach, not the reliever on the mound.
--
-- Known limitations (left out with a reason, never guessed):
--   * er / era are not produced -- earned runs require reconstructed-inning
--     logic (replay the inning without its errors) that cwevent does not
--     emit. `r` (total runs allowed) and season RA9 are the honest
--     event-derived figures; ERA is available per player-season from
--     raw.bref_pitching. Reconstructed-inning ER is a documented follow-up.
--   * 2026+ games (raw.mlb_playbyplay) are a separate builder.

INSERT INTO gold.pitching_game (
    game_id, player_id, team_id, season, game_date,
    gs, bf, outs, h, r, bb, ibb, so, hr, hbp, wp, bk, w, l, sv
)
WITH ev AS (
    SELECT
        g.id AS game_id,
        g.season,
        g.game_date,
        g.winning_pitcher_id,
        g.losing_pitcher_id,
        g.save_pitcher_id,
        re.resp_pit_id,
        re.resp_pit_start_fl,
        CASE WHEN re.bat_home_id = '1' THEN g.away_team_id ELSE g.home_team_id END AS team_id,
        re.event_cd,
        re.bat_event_fl,
        re.wp_fl,
        NULLIF(re.event_outs_ct, '')::integer   AS event_outs_ct,
        NULLIF(re.bat_dest_id, '')::integer     AS bat_dest_id,
        NULLIF(re.run1_dest_id, '')::integer    AS run1_dest_id,
        NULLIF(re.run2_dest_id, '')::integer    AS run2_dest_id,
        NULLIF(re.run3_dest_id, '')::integer    AS run3_dest_id,
        NULLIF(re.run1_resp_pit_id, '')         AS run1_resp_pit_id,
        NULLIF(re.run2_resp_pit_id, '')         AS run2_resp_pit_id,
        NULLIF(re.run3_resp_pit_id, '')         AS run3_resp_pit_id
    FROM core.game g
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = g.retro_game_id
    JOIN raw.retrosheet_event re ON re.game_id = g.retro_game_id
    WHERE g.retro_game_id IS NOT NULL
      AND lower(g.game_type) = 'regular'
      AND (%(season)s::integer IS NULL OR g.season = %(season)s::integer)
),
pitching AS (
    SELECT
        game_id, season, game_date, team_id, resp_pit_id AS pit_id,
        max(winning_pitcher_id) AS winning_pitcher_id,
        max(losing_pitcher_id)  AS losing_pitcher_id,
        max(save_pitcher_id)    AS save_pitcher_id,
        max(CASE WHEN resp_pit_start_fl = 'T' THEN 1 ELSE 0 END)               AS gs,
        count(*) FILTER (WHERE bat_event_fl = 'T')                             AS bf,
        coalesce(sum(event_outs_ct), 0)                                       AS outs,
        count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd IN ('20','21','22','23')) AS h,
        count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd IN ('14','15')) AS bb,
        count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd = '15')         AS ibb,
        count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd = '3')          AS so,
        count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd = '23')         AS hr,
        count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd = '16')         AS hbp,
        count(*) FILTER (WHERE wp_fl = 'T')                                    AS wp,
        count(*) FILTER (WHERE event_cd = '11')                               AS bk
    FROM ev
    WHERE resp_pit_id IS NOT NULL AND resp_pit_id <> ''
    GROUP BY game_id, season, game_date, team_id, resp_pit_id
    HAVING count(*) FILTER (WHERE bat_event_fl = 'T') > 0
),
runs AS (
    SELECT game_id, pit_id, count(*) AS r
    FROM (
        SELECT game_id, resp_pit_id      AS pit_id FROM ev WHERE bat_dest_id  >= 4
        UNION ALL
        SELECT game_id, run1_resp_pit_id FROM ev WHERE run1_dest_id >= 4 AND run1_resp_pit_id IS NOT NULL
        UNION ALL
        SELECT game_id, run2_resp_pit_id FROM ev WHERE run2_dest_id >= 4 AND run2_resp_pit_id IS NOT NULL
        UNION ALL
        SELECT game_id, run3_resp_pit_id FROM ev WHERE run3_dest_id >= 4 AND run3_resp_pit_id IS NOT NULL
    ) s
    WHERE pit_id IS NOT NULL AND pit_id <> ''
    GROUP BY game_id, pit_id
)
SELECT
    pg.game_id,
    p.id AS player_id,
    pg.team_id,
    pg.season,
    pg.game_date,
    pg.gs,
    pg.bf,
    pg.outs,
    pg.h,
    coalesce(r.r, 0) AS r,
    pg.bb, pg.ibb, pg.so, pg.hr, pg.hbp, pg.wp, pg.bk,
    coalesce((p.id = pg.winning_pitcher_id)::integer, 0) AS w,
    coalesce((p.id = pg.losing_pitcher_id)::integer, 0)  AS l,
    coalesce((p.id = pg.save_pitcher_id)::integer, 0)    AS sv
FROM pitching pg
JOIN core.player p ON p.retro_id = pg.pit_id
LEFT JOIN runs r ON r.game_id = pg.game_id AND r.pit_id = pg.pit_id
