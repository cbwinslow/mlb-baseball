-- Real final game scores from Retrosheet gameinfo (Plan 04D), for
-- comparing markov.simulate_game's simulated (away_runs, home_runs,
-- innings) against what actually happened.
--
-- raw.retrosheet_gameinfo's own vruns/hruns columns are the real final
-- scores (verified directly against a full spot-check sample: they match
-- MAX(away_score_ct)/MAX(home_score_ct) derived independently from
-- raw.retrosheet_event exactly). Innings played comes from
-- raw.retrosheet_event's own inn_ct (max across all recorded plays in
-- the game) since retrosheet_gameinfo's own `innings` column is
-- unpopulated in this dataset (confirmed: blank for every 2019
-- regular-season row). Same regular-season scoping as every sibling
-- markov_*.sql query, for the same reasons (postseason strategic
-- behavior bias).

WITH innings_played AS (
    SELECT re.game_id, max(re.inn_ct::int) AS innings
    FROM raw.retrosheet_event re
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = re.game_id AND lower(gi.gametype) = 'regular'
    WHERE gi._season = ANY(%(seasons)s)
    GROUP BY re.game_id
)
SELECT gi.gid, gi.vruns::int AS away_runs, gi.hruns::int AS home_runs, ip.innings
FROM raw.retrosheet_gameinfo gi
JOIN innings_played ip ON ip.game_id = gi.gid
WHERE gi._season = ANY(%(seasons)s) AND lower(gi.gametype) = 'regular';
