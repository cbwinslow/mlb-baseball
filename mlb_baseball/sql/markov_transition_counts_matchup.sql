-- Matchup-scoped copy of markov_transition_counts.sql (ADR-271).
-- Same destination-code rules and regular-season scope as the league
-- query; extra optional filters let Layer 2 estimate "this pitching
-- side vs this batting side" without changing the league estimator.
--
-- batting_team / pitching_team are Retrosheet team codes from
-- gameinfo.visteam / gameinfo.hometeam. When the batter is home
-- (bat_home_id = '1') the batting team is hometeam and the pitching
-- team is visteam; the away half-inning is the reverse.
--
-- pit_id is retrosheet_event.resp_pit_id (responsible pitcher), the
-- same identity starter.py uses. NULL skips the pitcher filter.
--
-- exclude_game_id drops that game's events (the target game must not
-- enter its own pre-game matchup sample).
--
-- before_date, when set, keeps only games whose Retrosheet gid encodes
-- a calendar date strictly before it (positions 4-11 of a standard
-- gid like ANA202104010). Non-standard test gids fail the regex and
-- are excluded by this filter — use exclude_game_id for those fixtures.

WITH scoped_events AS (
    SELECT
        re.outs_ct::int AS pre_outs,
        (re.base1_run_id IS NOT NULL) AS pre_b1,
        (re.base2_run_id IS NOT NULL) AS pre_b2,
        (re.base3_run_id IS NOT NULL) AS pre_b3,
        re.event_outs_ct::int AS outs_recorded,
        re.bat_dest_id::int AS bat_dest,
        re.run1_dest_id::int AS run1_dest,
        re.run2_dest_id::int AS run2_dest,
        re.run3_dest_id::int AS run3_dest,
        (re.bat_event_fl = 'T') AS is_pa
    FROM raw.retrosheet_event re
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = re.game_id AND lower(gi.gametype) = 'regular'
    WHERE gi._season = ANY(%(seasons)s)
      AND re.event_cd NOT IN ('0', '1')
      AND (%(bat_home)s::text IS NULL OR re.bat_home_id = %(bat_home)s::text)
      AND (
          %(batting_team)s::text IS NULL
          OR (
              (re.bat_home_id = '1' AND gi.hometeam = %(batting_team)s)
              OR (re.bat_home_id = '0' AND gi.visteam = %(batting_team)s)
          )
      )
      AND (
          %(pitching_team)s::text IS NULL
          OR (
              (re.bat_home_id = '1' AND gi.visteam = %(pitching_team)s)
              OR (re.bat_home_id = '0' AND gi.hometeam = %(pitching_team)s)
          )
      )
      AND (%(pit_id)s::text IS NULL OR re.resp_pit_id = %(pit_id)s)
      AND (%(exclude_game_id)s::text IS NULL OR re.game_id <> %(exclude_game_id)s)
      AND (
          %(before_date)s::date IS NULL
          OR (
              substring(gi.gid FROM 4 FOR 8) ~ '^[0-9]{8}$'
              AND to_date(substring(gi.gid FROM 4 FOR 8), 'YYYYMMDD')
                  < %(before_date)s::date
          )
      )
),
derived AS (
    SELECT
        pre_outs, pre_b1, pre_b2, pre_b3, is_pa,
        LEAST(pre_outs + outs_recorded, 3) AS post_outs,
        (bat_dest = 1)
            OR (pre_b1 AND run1_dest = 1)
            OR (pre_b2 AND run2_dest = 1)
            OR (pre_b3 AND run3_dest = 1) AS post_b1,
        (bat_dest = 2)
            OR (pre_b1 AND run1_dest = 2)
            OR (pre_b2 AND run2_dest = 2)
            OR (pre_b3 AND run3_dest = 2) AS post_b2,
        (bat_dest = 3)
            OR (pre_b1 AND run1_dest = 3)
            OR (pre_b2 AND run2_dest = 3)
            OR (pre_b3 AND run3_dest = 3) AS post_b3,
        (CASE WHEN bat_dest IN (4, 5, 6) THEN 1 ELSE 0 END
            + CASE WHEN pre_b1 AND run1_dest IN (4, 5, 6) THEN 1 ELSE 0 END
            + CASE WHEN pre_b2 AND run2_dest IN (4, 5, 6) THEN 1 ELSE 0 END
            + CASE WHEN pre_b3 AND run3_dest IN (4, 5, 6) THEN 1 ELSE 0 END
        ) AS runs_scored
    FROM scoped_events
)
SELECT pre_outs, pre_b1, pre_b2, pre_b3,
       post_outs, post_b1, post_b2, post_b3,
       runs_scored, count(*) AS n,
       count(*) FILTER (WHERE is_pa) AS n_pa
FROM derived
GROUP BY pre_outs, pre_b1, pre_b2, pre_b3, post_outs, post_b1, post_b2, post_b3, runs_scored;
