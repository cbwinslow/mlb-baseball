-- Retrosheet tie-out: season totals from the postseason and all-star game logs.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
--
-- The table has no _season column; the season is the year in the date
-- (YYYYMMDD). Used as the third source for register entry E1: other source
-- total minus regular-season game-log total equals this total.
SELECT
    left(date, 4) AS season,
    sum(v_homeruns::integer + h_homeruns::integer) AS hr,
    sum(v_strikeouts::integer + h_strikeouts::integer) AS k,
    sum(v_walks::integer + h_walks::integer) AS bb,
    sum(v_score::integer + h_score::integer) AS r,
    count(*) AS g
FROM raw.retrosheet_gamelog_post
WHERE left(date, 4) BETWEEN %(lo)s::text AND %(hi)s::text
GROUP BY left(date, 4)
ORDER BY left(date, 4)
