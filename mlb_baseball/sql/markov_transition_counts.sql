-- Raw base/out state transition counts from real Retrosheet play-by-play
-- (Plan 04D). One retrosheet_event row already carries both its own
-- pre-play state (outs_ct, base1/2/3_run_id) and everything needed to
-- derive its post-play state (event_outs_ct, bat_dest_id,
-- run1/2/3_dest_id) -- no sequential per-game walk is needed, this is a
-- single aggregate query over independently self-describing rows, unlike
-- the rolling-window shape every other retrosheet_event consumer here uses.
--
-- Destination codes, confirmed directly against real data (not assumed
-- from memory): 0 = batter/runner not advancing (out, for the batter --
-- batter is always "in play" for a plate appearance -- or simply "no
-- runner was there" when the matching base{N}_run_id is NULL); 1/2/3 =
-- first/second/third base; 4/5/6 = scored (4 = earned, 5/6 = unearned via
-- error or team-charged) -- verified real rows: bat_dest_id IN (5,6) rows
-- are hits/HRs with "(E..)"/"(UR)"/"(TUR)" annotations in event_tx, i.e.
-- genuinely scored, not a distinct "special" destination. Values above 6
-- do not occur in this data (confirmed via a full GROUP BY scan of both
-- bat_dest_id and run1_dest_id across the entire table).
--
-- event_cd = '1' ("no play", used for substitutions) and '0' (unknown)
-- carry no baserunning meaning and are excluded -- confirmed absent from
-- current data (a full event_cd GROUP BY scan found no '0'/'1' rows at
-- all), kept as a defensive filter in case future ingested data includes
-- them, not because it changes today's counts.
--
-- Scoped to regular-season games only (gi.gametype = 'regular'), matching
-- every sibling retrosheet_event consumer's convention (team_rate.py,
-- offense.py, starter.py) -- postseason strategic behavior (more sac
-- bunts/intentional walks in high-leverage spots) would bias a
-- league-average transition matrix if mixed in.
--
-- post_outs is capped at 3 (LEAST(...)): once the half-inning ends, base
-- occupancy stops mattering, so post_outs=3 rows are the shared terminal
-- state regardless of what post_b1/b2/b3 computed to -- collapsed
-- explicitly in Python (mlb_baseball/model/markov.py), not here, so this
-- query stays a plain, auditable GROUP BY.
--
-- runs_scored sums only bases that had a pre-play occupant (pre_b1/2/3)
-- plus the batter unconditionally (the batter always exists for the play)
-- -- a runner slot with no pre-play occupant reaching "4" cannot happen
-- (dest is 0 when base{N}_run_id is NULL, confirmed above), but the
-- explicit pre_b{n} AND guard makes that invariant visible in the query
-- itself rather than relying on it silently.
--
-- The bat_home parameter optionally scopes to one batting side only
-- ('1' = home, '0' = away) -- NULL (the default every existing caller
-- passes) means no filter, both sides combined, exactly this query's
-- original behavior. Added for Plan 04D's home/away split (ADR-080):
-- real per-play scoring rates genuinely differ by batting side in most
-- seasons (verified directly against real 2017 data: home batters
-- scored on about 3.3 of every 100 plate appearances, away batters
-- about 3.1 of every 100), so simulate_game can optionally draw each
-- side from its own estimated distribution instead of one combined
-- league-average one.

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
        re.run3_dest_id::int AS run3_dest
    FROM raw.retrosheet_event re
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = re.game_id AND lower(gi.gametype) = 'regular'
    WHERE gi._season = ANY(%(seasons)s)
      AND re.event_cd NOT IN ('0', '1')
      AND (%(bat_home)s::text IS NULL OR re.bat_home_id = %(bat_home)s::text)
),
derived AS (
    SELECT
        pre_outs, pre_b1, pre_b2, pre_b3,
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
       runs_scored, count(*) AS n
FROM derived
GROUP BY pre_outs, pre_b1, pre_b2, pre_b3, post_outs, post_b1, post_b2, post_b3, runs_scored;
