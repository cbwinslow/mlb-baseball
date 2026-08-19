-- Real per-half-inning run totals from Retrosheet play-by-play (Plan 04D),
-- for comparing markov.simulate_half_innings' simulated run distribution
-- against what actually happened -- the calibration check Plan 04D calls
-- for ("Calibrate composed distributions against held-out seasons and
-- real forward results").
--
-- Reuses the exact same runs_scored derivation as
-- markov_transition_counts.sql (destination codes IN (4,5,6) = scored;
-- see that file's own docstring for the verified mapping), summed across
-- every play in a (game_id, inn_ct, bat_home_id) group instead of grouped
-- by state transition. Same regular-season/event_cd scoping as that file,
-- for the same reasons (postseason strategic behavior bias; '0'/'1'
-- carry no baserunning meaning).
--
-- Only half-innings that actually reach 3 outs are included (the HAVING
-- clause below). A walk-off -- the home team taking the lead in the 9th
-- or later -- ends the game immediately, so that half-inning's play-by-play
-- stops before a 3rd out is ever recorded. markov.simulate_half_inning
-- always walks a simulated half-inning to TERMINAL (3 outs); comparing its
-- output against a real distribution that includes these truncated,
-- run-scoring-biased half-innings would be comparing two different
-- quantities. Confirmed real and non-negligible against real 2019 data:
-- 205 of 43,551 half-innings (0.47 percent) never reach 3 outs, and their mean
-- runs (1.585) is roughly 3x every other half-inning's (0.534) -- exactly
-- what "the play that ended the game was itself a scoring play" predicts.

WITH scoped_events AS (
    SELECT
        re.game_id,
        re.inn_ct,
        re.bat_home_id,
        re.outs_ct::int AS pre_outs,
        re.event_outs_ct::int AS event_outs,
        (re.base1_run_id IS NOT NULL) AS pre_b1,
        (re.base2_run_id IS NOT NULL) AS pre_b2,
        (re.base3_run_id IS NOT NULL) AS pre_b3,
        re.bat_dest_id::int AS bat_dest,
        re.run1_dest_id::int AS run1_dest,
        re.run2_dest_id::int AS run2_dest,
        re.run3_dest_id::int AS run3_dest
    FROM raw.retrosheet_event re
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = re.game_id AND lower(gi.gametype) = 'regular'
    WHERE gi._season = ANY(%(seasons)s)
      AND re.event_cd NOT IN ('0', '1')
),
play_runs AS (
    SELECT game_id, inn_ct, bat_home_id, pre_outs, event_outs,
        (CASE WHEN bat_dest IN (4, 5, 6) THEN 1 ELSE 0 END
            + CASE WHEN pre_b1 AND run1_dest IN (4, 5, 6) THEN 1 ELSE 0 END
            + CASE WHEN pre_b2 AND run2_dest IN (4, 5, 6) THEN 1 ELSE 0 END
            + CASE WHEN pre_b3 AND run3_dest IN (4, 5, 6) THEN 1 ELSE 0 END
        ) AS runs_scored
    FROM scoped_events
)
SELECT game_id, inn_ct, bat_home_id, sum(runs_scored) AS total_runs
FROM play_runs
GROUP BY game_id, inn_ct, bat_home_id
HAVING max(pre_outs + event_outs) = 3;
