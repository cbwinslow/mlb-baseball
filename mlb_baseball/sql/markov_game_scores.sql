-- Real final game scores from Retrosheet gameinfo (Plan 04D), for
-- comparing markov.simulate_game's simulated (away_runs, home_runs,
-- innings) against what actually happened.
--
-- raw.retrosheet_gameinfo's own vruns/hruns columns are the real final
-- scores (verified directly against a full spot-check sample: they match
-- MAX(away_score_ct)/MAX(home_score_ct) derived independently from
-- raw.retrosheet_event exactly; also confirmed never null/blank across
-- all 220,191 regular-season games in the database, every era). Innings
-- played comes from raw.retrosheet_event's own inn_ct (max across all
-- recorded plays in the game) since retrosheet_gameinfo's own `innings`
-- column is unpopulated in this dataset (confirmed: blank for every 2019
-- regular-season row). A game with no matching raw.retrosheet_event rows
-- at all (the same small, known, era-concentrated Retrosheet coverage
-- gap ADR-076 and ADR-034 already document) is silently excluded by the
-- inner join below, not passed through with a null innings value.
--
-- The season/gametype scope is applied once, in the outer WHERE, against
-- raw.retrosheet_gameinfo only -- the innings subquery below is a plain,
-- unfiltered aggregate over raw.retrosheet_event with no join of its own
-- (computing innings for every game, not just in-scope ones, is
-- harmless: the outer join only ever consumes the rows matching gi's own
-- filtered season/gametype selection).

WITH innings_played AS (
    SELECT game_id, max(inn_ct::int) AS innings
    FROM raw.retrosheet_event
    GROUP BY game_id
)
SELECT gi.gid, gi.vruns::int AS away_runs, gi.hruns::int AS home_runs, ip.innings
FROM raw.retrosheet_gameinfo gi
JOIN innings_played ip ON ip.game_id = gi.gid
WHERE gi._season = ANY(%(seasons)s) AND lower(gi.gametype) = 'regular';
