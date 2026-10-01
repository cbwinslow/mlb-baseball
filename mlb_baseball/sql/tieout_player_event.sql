-- Retrosheet tie-out: per player-game batting totals from the event files.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
-- The batter is resp_bat_id, not bat_id: when a plate appearance ends with a
-- different batter than it started with (an in-progress substitution --
-- injury, ejection), Retrosheet's own convention credits the statistical
-- result to the *responsible* batter (resp_bat_id), which is who the CSV
-- product (`batter` in tieout_player_csv_plays.sql/tieout_player_csv_batting.sql)
-- already credits it to. Grouping by bat_id instead was a real gate bug,
-- found by the first production run (task 4.1, results-2015-2025.md): every
-- one of ~250 "unexplained" player_game mismatches across all 11 seasons was
-- one of these substitutions, verified case by case against
-- raw.retrosheet_event's own resp_bat_id column, not a real data
-- disagreement. Runs scored are not attributed to a batter in the event
-- table, so r is not a player-game fact for this source. Called once per
-- season. Seasons before 1910 are excluded -- see tieout_season_event.sql for
-- why (this connector's own documented coverage starts in 1910).
WITH ev AS (
    SELECT DISTINCT ON (game_id, event_id)
        game_id, event_id, event_cd, bat_event_fl, resp_bat_id, _season
    FROM raw.retrosheet_event
    WHERE _season::integer BETWEEN %(lo)s AND %(hi)s
        AND _season::integer >= 1910
    ORDER BY game_id, event_id, _scope
)
SELECT
    _season AS season,
    game_id,
    resp_bat_id AS player_id,
    count(*) FILTER (WHERE bat_event_fl = 'T') AS pa,
    count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd = '3') AS k,
    count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd IN ('14', '15')) AS bb,
    count(*) FILTER (WHERE bat_event_fl = 'T' AND event_cd = '23') AS hr
FROM ev
GROUP BY _season, game_id, resp_bat_id
ORDER BY game_id, resp_bat_id
